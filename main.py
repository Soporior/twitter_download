import re
import time
from datetime import datetime
import httpx
import asyncio
import os
import json
import sys

sys.path.append('.')
from user_info import User_info
from db_log import db_log
from md_gen import md_gen
from cache_gen import cache_gen
from url_utils import quote_url

def del_special_char(string):
    string = re.sub(r'[^\u4e00-\u9fa5\u0030-\u0039\u0041-\u005a\u0061-\u007a\u3040-\u31FF\.]', '', string)
    return string

def stamp2time(msecs_stamp:int) -> str:
    timeArray = time.localtime(msecs_stamp/1000)
    otherStyleTime = time.strftime("%Y-%m-%d %H-%M", timeArray)
    return otherStyleTime

def time2stamp(timestr:str) -> int:
    datetime_obj = datetime.strptime(timestr, "%Y-%m-%d")
    msecs_stamp = int(time.mktime(datetime_obj.timetuple()) * 1000.0 + datetime_obj.microsecond / 1000.0)
    return msecs_stamp

def time_comparison(now, start, end):
    start_label = True
    start_down  = False
    #twitter : latest -> old
    if now >= start and now <= end:     #符合时间条件，下载
        start_down = True
    elif now < start:     #超出时间范围，结束
        start_label = False
    return [start_down, start_label]
    

#读取配置
log_output = False
has_retweet = False
has_highlights = False
has_likes = False
has_video = False
db_file = None
db_config = None
cache_data = None
down_log = False
autoSync = False
proxies = None
own_likes = False

md_file = None
md_output = True
media_count_limit = 0

start_time_stamp = 655028357000   #1990-10-04
end_time_stamp = 2548484357000    #2050-10-04
start_label = True
First_Page = True       #首页提取内容时特殊处理

with open('settings.json', 'r', encoding='utf8') as f:
    settings = json.load(f)

if not settings['save_path']:
    settings['save_path'] = os.getcwd()
settings['save_path'] += os.sep
if settings.get('own_likes'):
    own_likes = True
if settings['has_retweet'] and not own_likes:
    has_retweet = True
if settings['high_lights'] and not own_likes:
    has_highlights = True
    has_retweet = False
if settings['time_range']:
    time_range = True
    start_time,end_time = settings['time_range'].split(':')
    start_time_stamp,end_time_stamp = time2stamp(start_time),time2stamp(end_time)
if settings['autoSync']:
    autoSync = True
if settings['down_log']:
    down_log = True
if settings.get('likes') or own_likes:   #likes的逻辑和retweet大致相同
    has_retweet = True
    has_likes = True
    has_highlights = False
    start_time_stamp = 655028357000   #1990-10-04
    end_time_stamp = 2548484357000    #2050-10-04
if settings['has_video']:
    has_video = True
if settings['log_output']:
    log_output = True
if settings['max_concurrent_requests']:
    max_concurrent_requests = settings['max_concurrent_requests']
else:
    max_concurrent_requests = 8
###### proxy ######
if settings['proxy']:
    proxies = settings['proxy']
else:
    proxies = None

############
if settings['image_format'] == 'orig':
    orig_format = True
    img_format = 'jpg'
else:
    orig_format = False
    img_format = settings['image_format']

if not settings['md_output']:
    md_output = False

db_config = {
    'host': settings.get('db_host', '127.0.0.1'),
    'port': settings.get('db_port', 5432),
    'database': settings.get('db_name', 'twitter_download'),
    'user': settings.get('db_user', 'postgres'),
    'password': settings.get('db_password', '123456')
}

if settings['media_count_limit']:
    media_count_limit = settings['media_count_limit']

backup_stamp = start_time_stamp

def load_user_list():
    """从文件加载用户名列表"""
    user_file = settings.get('user_lst_file', 'user_list.txt')
    try:
        with open(user_file, 'r', encoding='utf-8') as f:
            users = [line.strip() for line in f if line.strip()]
        return users
    except FileNotFoundError:
        print(f"[ERROR] User list file not found: {user_file}")
        return []

def get_logged_in_screen_name():
    """从cookie识别当前登录账号的screen_name"""
    try:
        import re
        re_token = 'ct0=(.*?);'
        ct0_match = re.findall(re_token, settings['cookie'])
        if not ct0_match:
            print("[ERROR] cookie中缺少 ct0，无法识别登录账号")
            return None
        _headers['x-csrf-token'] = ct0_match[0]
    except Exception as e:
        print(f"[ERROR] 解析 cookie 中 ct0 失败: {e}")
        return None

    try:
        global request_count
        url = 'https://twitter.com/i/api/1.1/account/settings.json'
        response = httpx.get(url, headers=_headers, proxy=proxies, timeout=30.0).text
        request_count += 1
        raw_data = json.loads(response)
        screen_name = raw_data.get('screen_name')
        if not screen_name:
            print("[ERROR] 无法识别当前登录账号，请检查 cookie/auth_token/ct0 是否有效")
            if 'errors' in raw_data:
                print(f"[ERROR] Twitter API 返回错误: {raw_data['errors']}")
            return None
        return screen_name
    except Exception as e:
        print(f"[ERROR] 识别登录账号失败: {e}")
        return None

_headers = {
    'user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'authorization':'Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA',
}
_headers['cookie'] = settings['cookie']

request_count = 0    #请求次数计数
down_count = 0      #下载图片数计数

def log_error(error_type, location, error_msg, user_info=None, additional_info=None):
    """记录错误到本地文件"""
    error_log_file = 'error_log.txt'
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(error_log_file, 'a', encoding='utf-8') as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"时间: {timestamp}\n")
        f.write(f"错误类型: {error_type}\n")
        f.write(f"错误位置: {location}\n")
        if user_info:
            f.write(f"用户信息: {user_info.screen_name if hasattr(user_info, 'screen_name') else str(user_info)}\n")
        f.write(f"错误信息: {error_msg}\n")
        if additional_info:
            f.write(f"附加信息: {additional_info}\n")
        f.write(f"{'='*60}\n")

def save_last_user(screen_name):
    """保存当前处理的用户，下次运行从这里继续"""
    state_file = os.path.join(os.getcwd(), "last_run_state.json")
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({
                "last_user": screen_name,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 无法保存运行状态: {e}")

def clear_last_user():
    """清除保存的用户状态（全部处理完时调用）"""
    state_file = os.path.join(os.getcwd(), "last_run_state.json")
    try:
        if os.path.exists(state_file):
            os.remove(state_file)
    except Exception as e:
        print(f"[WARN] 无法清除运行状态: {e}")

def get_last_user():
    """获取上次中断的用户"""
    state_file = os.path.join(os.getcwd(), "last_run_state.json")
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("last_user")
        except Exception:
            pass
    return None

def get_other_info(_user_info):
    url = 'https://twitter.com/i/api/graphql/xc8f1g7BYqr6VTzTbvNlGw/UserByScreenName?variables={"screen_name":"' + _user_info.screen_name + '","withSafetyModeUserFields":false}&features={"hidden_profile_likes_enabled":false,"hidden_profile_subscriptions_enabled":false,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"subscriptions_verification_info_verified_since_enabled":true,"highlights_tweets_tab_ui_enabled":true,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true}&fieldToggles={"withAuxiliaryUserLabels":false}'
    response = None
    try:
        global request_count
        response = httpx.get(quote_url(url), headers=_headers, proxy=proxies, timeout=30.0).text
        request_count += 1
        raw_data = json.loads(response)

        # 检查用户是否被封禁或不存在
        user_result = raw_data.get('data', {}).get('user', {}).get('result', {})
        if user_result.get('__typename') == 'UserUnavailable':
            reason = user_result.get('reason', 'Unknown')
            msg = user_result.get('message', 'User unavailable')
            print(f'[WARN] 用户 {_user_info.screen_name} 无法访问: {msg} ({reason})')
            log_error("用户不可用", "get_other_info", f"用户被封禁或注销: {reason}", _user_info, msg)
            return 'user_unavailable'

        _user_info.rest_id = raw_data['data']['user']['result']['rest_id']
        _user_info.name = raw_data['data']['user']['result']['legacy']['name']
        _user_info.statuses_count = raw_data['data']['user']['result']['legacy']['statuses_count']
        _user_info.media_count = raw_data['data']['user']['result']['legacy']['media_count']
    except Exception as e:
        error_msg = str(e)
        location = f"main.py:get_other_info"
        print(f'[ERROR] 获取用户 {_user_info.screen_name} 信息失败: {error_msg}')
        if response:
            if 'User unavailable' in response or 'suspended' in response.lower():
                log_error("用户不可用", location, error_msg, _user_info, "用户被封禁或注销")
                return 'user_unavailable'
            log_error("获取用户信息失败", location, error_msg, _user_info, f"响应: {response[:500]}")
        else:
            print("请求未完成，未获取到响应")
            log_error("获取用户信息失败", location, error_msg, _user_info, "请求未完成")
        return False
    return True

def print_info(_user_info):
    print(
        f'''
        <======基本信息=====>
        昵称:{_user_info.name.encode('utf-8', errors='replace').decode('utf-8')}
        用户名:{_user_info.screen_name}
        数字ID:{_user_info.rest_id}
        总推数(含转推):{_user_info.statuses_count}
        含图片/视频/音频推数(不含转推):{_user_info.media_count}
        <==================>
        开始爬取...
        '''
    )

def get_download_url(_user_info):

    def get_heighest_video_quality(variants) -> str:   #找到最高质量的视频地址,并返回

        if len(variants) == 1:      #gif适配
            return variants[0]['url']
        
        max_bitrate = 0
        heighest_url = None
        for i in variants:
            if 'bitrate' in i:
                if int(i['bitrate']) > max_bitrate:
                    max_bitrate = int(i['bitrate'])
                    heighest_url = i['url']
        return heighest_url


    def get_url_from_content(content):
        global start_label
        _photo_lst = []
        if has_retweet or has_highlights:
            x_label = 'content'
        else:
            x_label = 'item'
        for i in content:
            try:
                if 'promoted-tweet' in i['entryId']:        #排除广告
                    continue
                if 'tweet' in i['entryId']:     #正常推文
                    if 'tweet' in i[x_label]['itemContent']['tweet_results']['result']:
                        a = i[x_label]['itemContent']['tweet_results']['result']['tweet']['legacy']       #适配限制回复账号
                        frr = [a['favorite_count'], a['retweet_count'], a['reply_count']]
                        tweet_msecs = int(i[x_label]['itemContent']['tweet_results']['result']['tweet']['edit_control']['editable_until_msecs']) - 3600000
                    else:
                        a = i[x_label]['itemContent']['tweet_results']['result']['legacy']
                        frr = [a['favorite_count'], a['retweet_count'], a['reply_count']]
                        tweet_msecs = int(i[x_label]['itemContent']['tweet_results']['result']['edit_control']['editable_until_msecs']) - 3600000
                    timestr = stamp2time(tweet_msecs)

                    #我知道这边代码很烂
                    #但我实在不想重构 ( º﹃º )

                    _result = time_comparison(tweet_msecs, start_time_stamp, end_time_stamp)
                    if _result[0]:  #符合时间限制
                        if 'retweeted_status_result' not in a : #判断是否为转推,以及是否获取转推
                            name = _user_info.name
                            screen_name = _user_info.screen_name
                            prefix_suffix = ''
                            if has_likes:
                                a2 = i[x_label]['itemContent']['tweet_results']['result']['core']['user_results']['result']['legacy']
                                name = a2['name']
                                screen_name = a2['screen_name']
                                prefix_suffix = '-liked'
                            if 'extended_entities' in a:
                                _photo_lst += [(get_heighest_video_quality(_media['video_info']['variants']), f'{timestr}-vid{prefix_suffix}', [tweet_msecs, name, f'@{screen_name}', _media['expanded_url'], 'Video', get_heighest_video_quality(_media['video_info']['variants']), '', a['full_text']] + frr) if 'video_info' in _media and has_video else (_media['media_url_https'], f'{timestr}-img{prefix_suffix}', [tweet_msecs, name, f'@{screen_name}', _media['expanded_url'], 'Image', _media['media_url_https'], '', a['full_text']] + frr) for _media in a['extended_entities']['media']]

                        elif has_retweet:
                            name = a['retweeted_status_result']['result']['core']['user_results']['result']['legacy']['name']
                            screen_name = a['retweeted_status_result']['result']['core']['user_results']['result']['legacy']['screen_name']
                            full_text = a['retweeted_status_result']['result']['legacy']['full_text']
                            id_str = a['retweeted_status_result']['result']['legacy']['id_str']
                            
                            if 'extended_entities' in a['retweeted_status_result']['result']['legacy'] and screen_name != _user_info.screen_name:
                                _photo_lst += [(get_heighest_video_quality(_media['video_info']['variants']), f'{timestr}-vid-retweet', [tweet_msecs, name, f"@{screen_name}", _media['expanded_url'], 'Video', get_heighest_video_quality(_media['video_info']['variants']), '', full_text] + frr) if 'video_info' in _media and has_video else (_media['media_url_https'], f'{timestr}-img-retweet', [tweet_msecs, name, f"@{screen_name}", _media['expanded_url'], 'Image', _media['media_url_https'], '', full_text] + frr) for _media in a['retweeted_status_result']['result']['legacy']['extended_entities']['media']]

                    elif not _result[1]:    #已超出目标时间范围
                        start_label = False
                        break
                
                elif 'profile-conversation' in i['entryId']:    #回复的推文(对话线索)
                    if 'tweet' in i[x_label]['items'][0]['item']['itemContent']['tweet_results']['result']:
                        a = i[x_label]['items'][0]['item']['itemContent']['tweet_results']['result']['tweet']['legacy']
                        frr = [a['favorite_count'], a['retweet_count'], a['reply_count']]
                        tweet_msecs = int(i[x_label]['items'][0]['item']['itemContent']['tweet_results']['result']['tweet']['edit_control']['editable_until_msecs']) - 3600000
                    else:
                        a = i[x_label]['items'][0]['item']['itemContent']['tweet_results']['result']['legacy']
                        frr = [a['favorite_count'], a['retweet_count'], a['reply_count']]
                        tweet_msecs = int(i[x_label]['items'][0]['item']['itemContent']['tweet_results']['result']['edit_control']['editable_until_msecs']) - 3600000
                    timestr = stamp2time(tweet_msecs)

                    _result = time_comparison(tweet_msecs, start_time_stamp, end_time_stamp)
                    if _result[0]:  #符合时间限制
                        if 'extended_entities' in a:
                            _photo_lst += [(get_heighest_video_quality(_media['video_info']['variants']), f'{timestr}-vid', [tweet_msecs, _user_info.name, f'@{_user_info.screen_name}', _media['expanded_url'], 'Video', get_heighest_video_quality(_media['video_info']['variants']), '', a['full_text']] + frr) if 'video_info' in _media and has_video else (_media['media_url_https'], f'{timestr}-img', [tweet_msecs, _user_info.name, f'@{_user_info.screen_name}', _media['expanded_url'], 'Image', _media['media_url_https'], '', a['full_text']] + frr) for _media in a['extended_entities']['media']]
                    elif not _result[1]:    #已超出目标时间范围
                        start_label = False
                        break

            except Exception as e:
                continue
            if 'cursor-bottom' in i['entryId']:     #更新下一页的请求编号(含转推模式&亮点模式)
                _user_info.cursor = i['content']['value']

        return _photo_lst

    print(f'已下载图片/视频:{_user_info.count}')
    if has_highlights: ##2024-01-05 #适配[亮点]标签
        url_top = 'https://twitter.com/i/api/graphql/w9-i9VNm_92GYFaiyGT1NA/UserHighlightsTweets?variables={"userId":"' + _user_info.rest_id + '","count":20,'
        url_bottom = '"includePromotedContent":true,"withVoice":true}&features={"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"c9s_tweet_anatomy_moderator_badge_enabled":true,"tweetypie_unmention_optimization_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":false,"tweet_awards_web_tipping_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"rweb_video_timestamps_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_media_download_video_enabled":false,"responsive_web_enhance_cards_enabled":false}'
    elif has_likes:
        url_top = 'https://twitter.com/i/api/graphql/-fbTO1rKPa3nO6-XIRgEFQ/Likes?variables={"userId":"' + _user_info.rest_id + '","count":200,'
        url_bottom = '"includePromotedContent":false,"withClientEventToken":false,"withBirdwatchNotes":false,"withVoice":true,"withV2Timeline":true}&features={"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"c9s_tweet_anatomy_moderator_badge_enabled":true,"tweetypie_unmention_optimization_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":false,"tweet_awards_web_tipping_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"rweb_video_timestamps_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_media_download_video_enabled":false,"responsive_web_enhance_cards_enabled":false}'
    elif has_retweet:     #包含转推调用[UserTweets]的API(调用一次上限返回20条)
        url_top = 'https://twitter.com/i/api/graphql/2GIWTr7XwadIixZDtyXd4A/UserTweets?variables={"userId":"' + _user_info.rest_id + '","count":20,'
        url_bottom = '"includePromotedContent":false,"withQuickPromoteEligibilityTweetFields":true,"withVoice":true,"withV2Timeline":true}&features={"rweb_lists_timeline_redesign_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"tweetypie_unmention_optimization_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":false,"tweet_awards_web_tipping_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_media_download_video_enabled":false,"responsive_web_enhance_cards_enabled":false}&fieldToggles={"withAuxiliaryUserLabels":false,"withArticleRichContentState":false}'
    else:       #不包含转推则调用[UserMedia]的API(返回条数貌似无上限/改count) ##2023-12-11#此模式API返回值变动
        url_top = 'https://twitter.com/i/api/graphql/Le6KlbilFmSu-5VltFND-Q/UserMedia?variables={"userId":"' + _user_info.rest_id + '","count":500,'
        url_bottom = '"includePromotedContent":false,"withClientEventToken":false,"withBirdwatchNotes":false,"withVoice":true,"withV2Timeline":true}&features={"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"tweetypie_unmention_optimization_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":false,"tweet_awards_web_tipping_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_media_download_video_enabled":false,"responsive_web_enhance_cards_enabled":false}'

    if _user_info.cursor:
        url = url_top + '"cursor":"' + _user_info.cursor + '",' + url_bottom
    else:
        url = url_top + url_bottom      #第一页,无cursor
    response = None
    retry_count = 0
    max_retries = 3
    while retry_count < max_retries:
        try:
            global request_count
            response = httpx.get(quote_url(url), headers=_headers, proxy=proxies, timeout=30.0).text
            request_count += 1
            break
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f'[ERROR] 请求失败，已重试{max_retries}次: {str(e)}')
                log_error("网络请求失败", "get_download_url", f"重试{max_retries}次后失败: {str(e)}", _user_info)
                return False
            print(f'[WARN] 请求失败，第{retry_count}次重试: {str(e)}')
            import asyncio
            asyncio.sleep(2)  # 等待2秒后重试
    try:
        raw_data = json.loads(response)
    except Exception:
        if 'Rate limit exceeded' in response:
            print('API次数已超限')
            # 保存当前用户，下次从这里继续
            save_last_user(_user_info.screen_name)
            print(f'[INFO] 已保存进度：下次运行从用户 {_user_info.screen_name} 继续')
            print('[INFO] 程序退出')
            sys.exit(1)
        else:
            print('获取数据失败')
        print(response)
        return []

    try:
        if has_highlights:  #亮点模式
            raw_data = raw_data['data']['user']['result']['timeline']['timeline']['instructions'][-1]['entries']
        elif has_retweet:   #与likes共用
            raw_data = raw_data['data']['user']['result']['timeline_v2']['timeline']['instructions'][-1]['entries']
        else:   #usermedia模式
            raw_data = raw_data['data']['user']['result']['timeline_v2']['timeline']['instructions']

        if (has_retweet or has_highlights) and 'cursor-top' in raw_data[0]['entryId']:
            return []

        if not has_retweet and not has_highlights:     #usermedia模式下的下一页请求编号
            for i in raw_data[-1]['entries']:
                if 'bottom' in i['entryId']:
                    _user_info.cursor = i['content']['value']
    except Exception as e:
        print(f'获取推文信息错误: {e}')
        log_error("获取推文信息错误", "get_download_url", str(e), _user_info, f"响应: {response[:500] if response else 'None'}")
        return []

    photo_lst = []
    if start_label:
        if not has_retweet and not has_highlights:
            global First_Page
            if First_Page:
                first_entry = raw_data[-1]['entries'][0]['content']
                if 'items' in first_entry:
                    raw_data = first_entry['items']
                elif 'moduleItems' in first_entry:
                    raw_data = first_entry['moduleItems']
                else:
                    print('推文列表为空或API结构变化')
                    return [True]
                First_Page = False
            else:
                if 'moduleItems' in raw_data[0]:
                    raw_data = raw_data[0]['moduleItems']
                else:
                    return []

        photo_lst = get_url_from_content(raw_data)

    if not photo_lst:
        photo_lst = [True]
    return photo_lst

def download_control(_user_info):
    async def _main():
        async def down_save(url, prefix, csv_info, order: int):
            is_video = '.mp4' in url or csv_info[4] == 'Video'
            if is_video:
                _file_name = f'{_user_info.save_path_videos + os.sep}{prefix}_{_user_info.count + order}.mp4'
            else:
                try:
                    if orig_format:
                        url += f'?name=orig'
                        _file_name = f'{_user_info.save_path_images + os.sep}{prefix}_{_user_info.count + order}.{csv_info[5][-3:]}' # 根据图片 url 获取原始格式
                    else: # 指定格式时，先使用 name=orig，404 则切回 name=4096x4096，以保证最大尺寸
                        _file_name = f'{_user_info.save_path_images + os.sep}{prefix}_{_user_info.count + order}.{img_format}'
                        if img_format != 'png':
                            url += f'?format=jpg&name=4096x4096'
                        else:
                            url += f'?format=png&name=4096x4096'
                except Exception as e:
                    print(url)
                    return False

            # 先检查本地文件是否已经存在且大于0，存在直接跳过
            if os.path.exists(_file_name) and os.path.getsize(_file_name) > 0:
                if log_output:
                    print(f'{_file_name}=====>文件已存在，跳过')
                return

            csv_info[-5] = os.path.split(_file_name)[1]
            if md_output: # 在下载完毕之前先输出到 Markdown，以尽可能保证高并发下载也能得到正确的推文顺序。
                md_file.media_tweet_input(csv_info, prefix)
            count = 0
            while True:
                try:
                    async with semaphore:
                        async with httpx.AsyncClient(proxy=proxies) as client:
                            global down_count
                            response = await client.get(quote_url(url), timeout=(3.05, 16))        #如果出现第五次或以上的下载失败,且确认不是网络问题,可以适当降低最大并发数量
                            if response.status_code == 404:
                                raise Exception('404')
                            down_count += 1
                    with open(_file_name,'wb') as f:
                        f.write(response.content)

                    db_file.data_input(csv_info)

                    if log_output:
                        print(f'{_file_name}=====>下载完成')

                    break
                except Exception as e:
                    if '.mp4' in url or orig_format or str(e) != "404":
                        count += 1
                        if count >= 10:
                            print(f'{_file_name}=====>第{count}次下载失败，已跳过该文件。')
                            print(url)
                            break
                        print(f'{_file_name}=====>第{count}次下载失败,正在重试')
                        print(url)
                    else:
                        url = url.replace('name=orig', 'name=4096x4096')

        while True:
            photo_lst = get_download_url(_user_info)
            if not photo_lst:
                break
            elif photo_lst[0] == True:
                continue
            semaphore = asyncio.Semaphore(max_concurrent_requests)    #最大并发数量，默认为8，对自己网络有自信的可以调高
            if down_log:
                await asyncio.gather(*[asyncio.create_task(down_save(url[0], url[1], url[2], order)) for order,url in enumerate(photo_lst) if cache_data.is_present(url[0])])
            else:
                await asyncio.gather(*[asyncio.create_task(down_save(url[0], url[1], url[2], order)) for order,url in enumerate(photo_lst)])
            _user_info.count += len(photo_lst)      #更新计数

    asyncio.run(_main())

def main(_user_info: object):
    re_token = 'ct0=(.*?);'
    _headers['x-csrf-token'] = re.findall(re_token,_headers['cookie'])[0]
    _headers['referer'] = 'https://twitter.com/' + _user_info.screen_name
    user_result = get_other_info(_user_info)
    if user_result == 'user_unavailable':
        print(f'用户 {_user_info.screen_name} 被封禁或注销，已跳过')
        return None
    elif not user_result:
        print(f'用户 {_user_info.screen_name} 获取信息失败，跳过该用户继续处理下一个')
        log_error("用户信息获取失败", "main.py:main (第395行)", f"用户 {_user_info.screen_name} 的信息获取失败，已跳过", _user_info)
        return False
    print_info(_user_info)
    # 映射文件：记录 screen_name -> folder_name
    map_file = os.path.join(os.getcwd(), "user_folder_map.json")
    folder_map = {}
    if os.path.exists(map_file):
        try:
            with open(map_file, "r", encoding="utf-8") as f:
                folder_map = json.load(f)
        except Exception:
            pass

    safe_name = del_special_char(_user_info.name) if _user_info.name else ""
    screen_name = _user_info.screen_name
    save_dir = settings['save_path']

    # ========== 步骤1：确定想要的文件夹名（优先用当前昵称） ==========
    desired_name = safe_name if safe_name else screen_name

    # ========== 步骤2：查找当前用户已有的文件夹 ==========
    existing_path = None
    existing_name = None

    # 先从映射找
    if screen_name in folder_map:
        info = folder_map[screen_name]
        existing_name = info.get("folder_name", None) if isinstance(info, dict) else info
        if existing_name:
            test_path = os.path.join(save_dir, existing_name)
            if os.path.isdir(test_path):
                existing_path = test_path

    # 如果映射没找到，搜索旧格式
    if not existing_path:
        try:
            if os.path.exists(save_dir):
                for entry in os.listdir(save_dir):
                    entry_path = os.path.join(save_dir, entry)
                    if not os.path.isdir(entry_path):
                        continue
                    # 匹配旧格式：纯 id、id_*、*_id
                    if entry == screen_name or entry.startswith(screen_name + "_") or entry.endswith("_" + screen_name):
                        existing_path = entry_path
                        existing_name = entry
                        break
        except Exception:
            pass

    # ========== 步骤3：决定最终文件夹名 ==========
    target_name = desired_name
    target_path = os.path.join(save_dir, target_name)

    # 检查 desired_name 是否被其他用户占用
    conflict = False
    for sn, info in folder_map.items():
        fn = info.get("folder_name", None) if isinstance(info, dict) else info
        if fn == desired_name and sn != screen_name:
            conflict = True
            break

    # 如果冲突，或者文件夹已存在且不是我们的，加序号
    if conflict or (os.path.exists(target_path) and (not existing_path or os.path.normcase(target_path) != os.path.normcase(existing_path))):
        counter = 1
        while True:
            test_name = f"{desired_name}_{counter}"
            test_path = os.path.join(save_dir, test_name)

            # 检查这个名字是否被占用
            occupied = False
            for sn, info in folder_map.items():
                fn = info.get("folder_name", None) if isinstance(info, dict) else info
                if fn == test_name and sn != screen_name:
                    occupied = True
                    break
            if not occupied and not os.path.exists(test_path):
                target_name = test_name
                target_path = test_path
                break
            counter += 1

    # ========== 步骤4：重命名文件夹（如果需要） ==========
    if existing_path and os.path.normcase(existing_path) != os.path.normcase(target_path):
        try:
            print(f"[INFO] 更新文件夹名：{os.path.basename(existing_path)} -> {target_name}")
            os.rename(existing_path, target_path)
            existing_path = target_path
        except Exception as e:
            print(f"[WARN] 文件夹重命名失败，继续使用原文件夹：{e}")
            target_path = existing_path
            target_name = os.path.basename(existing_path)

    # ========== 步骤5：更新映射文件 ==========
    folder_map[screen_name] = {
        "nickname": safe_name,
        "folder_name": target_name
    }
    try:
        with open(map_file, "w", encoding="utf-8") as f:
            json.dump(folder_map, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] 无法保存映射文件：{e}")

    _path = target_path

    if not os.path.exists(_path):   #创建文件夹
        os.makedirs(_path)                          #用户名建文件夹
        os.makedirs(os.path.join(_path, 'images'))  #图片子文件夹
        os.makedirs(os.path.join(_path, 'videos'))  #视频子文件夹
    _user_info.save_path = _path
    _user_info.save_path_images = os.path.join(_path, 'images')
    _user_info.save_path_videos = os.path.join(_path, 'videos')

    global db_file
    db_file = db_log(_user_info.save_path, _user_info.name, _user_info.screen_name, settings['time_range'], db_config)

    if md_output:
        global md_file
        md_file = md_gen(_user_info.save_path, _user_info.name, _user_info.screen_name, settings['time_range'], has_likes, media_count_limit)

    if down_log:
        global cache_data
        cache_data = cache_gen(_user_info.save_path)

    if autoSync:
        # 扫描 images 和 videos 文件夹
        image_files = sorted(os.listdir(_user_info.save_path_images)) if os.path.exists(_user_info.save_path_images) else []
        video_files = sorted(os.listdir(_user_info.save_path_videos)) if os.path.exists(_user_info.save_path_videos) else []
        files = image_files + video_files
        if len(files) > 0:
            global start_time_stamp
            re_rule = r'\d{4}-\d{2}-\d{2}'
            for i in files[::-1]:
                if "-img_" in i or "-vid_" in i:
                    start_time_stamp = time2stamp(re.findall(re_rule, i)[0])
                    break
            else:
                start_time_stamp = backup_stamp
        else:
            start_time_stamp = backup_stamp

    download_control(_user_info)

    db_file.db_close()

    if md_output:
        md_file.md_close()

    if down_log:
        del cache_data
    print(f'{_user_info.name}下载完成\n\n')

if __name__=='__main__':
    _start = time.time()
    if own_likes:
        # 第一阶段：下载自己的 Likes
        screen_name = "laoniuer"
        print(f"[INFO] 第一阶段：下载账号 {screen_name} 的 Likes")
        main(User_info(screen_name))
        start_label = True
        First_Page = True

        # 第二阶段：重置模式为下载用户自己发的内容
        print("\n[INFO] 第二阶段：下载 user_list.txt 中用户自己发的内容")
        has_retweet = settings['has_retweet']
        has_likes = False
        has_highlights = settings['high_lights']
        if settings['time_range']:
            start_time,end_time = settings['time_range'].split(':')
            start_time_stamp,end_time_stamp = time2stamp(start_time),time2stamp(end_time)
        else:
            start_time_stamp = backup_stamp

    # 下载 user_list.txt 里的用户
    user_list = load_user_list()
    if not user_list:
        if not own_likes:
            print("[ERROR] No users to download. Please check user_list.txt")
            sys.exit(1)
        else:
            print("[INFO] user_list.txt 为空或不存在，跳过下载用户自己发的内容")
    else:
        print(f"[INFO] Loaded {len(user_list)} users")

        # 检查是否有上次中断的用户
        last_user = get_last_user()
        start_index = 0
        if last_user:
            if last_user in user_list:
                start_index = user_list.index(last_user)
                print(f"[INFO] 检测到上次中断，从用户 {last_user} 继续（第 {start_index + 1} 个）")
            else:
                print(f"[INFO] 上次中断的用户 {last_user} 不在当前列表中，从头开始")

        # 从上次中断的位置继续
        for i in user_list[start_index:]:
            main(User_info(i))
            start_label = True
            First_Page = True

    # 全部处理完，清除保存的进度
    clear_last_user()
    print(f'共耗时:{time.time()-_start}秒\n共调用{request_count}次API\n共下载{down_count}份图片/视频')

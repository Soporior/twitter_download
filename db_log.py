import psycopg2
import psycopg2.extras
import time
from datetime import datetime

class db_log():
    def __init__(self, save_path: str, user_name: str, screen_name: str, tweet_range: str, db_config: dict) -> None:
        """
        数据库日志模块 - 每个用户一个表

        Args:
            save_path: 保存路径
            user_name: 显示名称
            screen_name: 用户名(作为表名)
            tweet_range: 推文时间范围
            db_config: 数据库配置
        """
        self.db_config = db_config
        self.conn = None
        self.cursor = None

        # 清理表名中的非法字符
        table_name = self._sanitize_table_name(screen_name)
        self.table_name = table_name

        try:
            # 连接数据库
            self.conn = psycopg2.connect(
                host=db_config.get('host', '127.0.0.1'),
                port=db_config.get('port', 5432),
                database=db_config.get('database', 'twitter_download'),
                user=db_config.get('user', 'postgres'),
                password=db_config.get('password', '123456')
            )
            self.cursor = self.conn.cursor()

            # 创建用户表
            self._create_table(table_name)

            # 写入表头信息
            self._write_metadata(table_name, user_name, screen_name, tweet_range, save_path)

        except Exception as e:
            print(f"数据库连接失败，已跳过数据库记录: {e}")
            self.conn = None
            self.cursor = None

    def _sanitize_table_name(self, name: str) -> str:
        """清理表名，只保留字母数字和下划线"""
        import re
        return re.sub(r'[^a-zA-Z0-9_]', '_', name)

    def _create_table(self, table_name: str) -> None:
        """创建日志表"""
        create_sql = f"""
        CREATE TABLE IF NOT EXISTS "{table_name}" (
            id SERIAL PRIMARY KEY,
            tweet_date TIMESTAMP,
            display_name VARCHAR(255),
            user_name VARCHAR(255),
            tweet_url TEXT,
            media_type VARCHAR(50),
            media_url TEXT,
            saved_filename VARCHAR(500),
            tweet_content TEXT,
            favorite_count INTEGER DEFAULT 0,
            retweet_count INTEGER DEFAULT 0,
            reply_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        self.cursor.execute(create_sql)
        self.conn.commit()

        # 创建索引以加速查询
        try:
            self.cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_tweet_date ON "{table_name}" (tweet_date);')
            self.cursor.execute(f'CREATE INDEX IF NOT EXISTS idx_{table_name}_media_type ON "{table_name}" (media_type);')
            self.conn.commit()
        except:
            pass

    def _write_metadata(self, table_name: str, user_name: str, screen_name: str, tweet_range: str, save_path: str) -> None:
        """写入元数据到数据库配置表"""
        # 创建配置表（如果不存在）
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS download_config (
                id SERIAL PRIMARY KEY,
                screen_name VARCHAR(255) UNIQUE,
                user_name VARCHAR(255),
                tweet_range VARCHAR(100),
                save_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 插入或更新配置
        self.cursor.execute("""
            INSERT INTO download_config (screen_name, user_name, tweet_range, save_path)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (screen_name) DO UPDATE SET
                user_name = EXCLUDED.user_name,
                tweet_range = EXCLUDED.tweet_range,
                save_path = EXCLUDED.save_path;
        """, (screen_name, user_name, tweet_range, save_path))

        self.conn.commit()

    def stamp2time(self, msecs_stamp: int) -> str:
        """毫秒时间戳转字符串"""
        timeArray = time.localtime(msecs_stamp / 1000)
        return time.strftime("%Y-%m-%d %H:%M", timeArray)

    def stamp2datetime(self, msecs_stamp: int) -> datetime:
        """毫秒时间戳转 datetime 对象"""
        return datetime.fromtimestamp(msecs_stamp / 1000)

    def data_input(self, main_par_info: list) -> None:
        """
        写入单条日志数据
        数据格式: [tweet_date, display_name, user_name, tweet_url, media_type, media_url, saved_filename, tweet_content, favorite_count, retweet_count, reply_count]
        """
        if not self.cursor:
            return

        try:
            # 转换时间戳为 datetime
            tweet_date = self.stamp2datetime(main_par_info[0])

            insert_sql = f"""
                INSERT INTO "{self.table_name}" (
                    tweet_date, display_name, user_name, tweet_url, media_type,
                    media_url, saved_filename, tweet_content, favorite_count,
                    retweet_count, reply_count
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """

            self.cursor.execute(insert_sql, (
                tweet_date,
                main_par_info[1],          # display_name
                main_par_info[2],          # user_name
                main_par_info[3],          # tweet_url
                main_par_info[4],          # media_type
                main_par_info[5],          # media_url
                main_par_info[6],          # saved_filename
                main_par_info[7],          # tweet_content
                main_par_info[8] if len(main_par_info) > 8 else 0,   # favorite_count
                main_par_info[9] if len(main_par_info) > 9 else 0,  # retweet_count
                main_par_info[10] if len(main_par_info) > 10 else 0  # reply_count
            ))

        except Exception as e:
            print(f"写入数据库失败: {e}")

    def db_close(self) -> None:
        """关闭数据库连接"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.commit()
            self.conn.close()

    def get_stats(self) -> dict:
        """获取当前用户下载统计"""
        try:
            self.cursor.execute(f'SELECT COUNT(*) FROM "{self.table_name}";')
            total = self.cursor.fetchone()[0]

            self.cursor.execute(f'SELECT COUNT(*) FROM "{self.table_name}" WHERE media_type = \'Image\';')
            images = self.cursor.fetchone()[0]

            self.cursor.execute(f'SELECT COUNT(*) FROM "{self.table_name}" WHERE media_type = \'Video\';')
            videos = self.cursor.fetchone()[0]

            return {'total': total, 'images': images, 'videos': videos}
        except:
            return {'total': 0, 'images': 0, 'videos': 0}

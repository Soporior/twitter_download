/*
 * @Author: soporior-house zeref13@live.com
 * @Date: 2026-03-18 22:31:38
 * @LastEditors: soporior-house zeref13@live.com
 * @LastEditTime: 2026-03-18 22:31:43
 * @FilePath: \twitter_download\去重.js
 * @Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
 */
const str = "yuanyepi,intheshallow5,Denielvalles,daniuzibaobao,buxianliu,REISON19991102,Hunkyhuang,jichemeng98,quc88068418,jackonjiang,BeastBroUno,patr1ckbyte,Topqis1,randall612345,stack_sorcerer,heiwushiyinghan,zhenghao1314,PLm0168,MilkingNANTU,PPAP_202,Tigershark1833,Murphy_ZhaoC,thicchiom,Jann49224729,ysxq17,Hunkyhuang,KJ12713276,kumabearcarino,Isu1ItbaIpo,jekrabbit8,buxiangshuisha,xhx_93,Peinin8888,xiaorxiaor,katu9805,fm16970,Damgooooo,tenji_89,tuobadanke,daziyizhikaixin,asheridan68,KIDDEN7777777,maxwellmillers,zdx1xx,Museumans,a6653578,max06734521,kkrobin_,Exp_lam,nword_kritzhang,Maxing2020,MAN2QQ,LaFei2531,LJxZcvufpflyDtT,AuRevoir_178,pec_pal,Cup_pio,katu9805,dedaeleio,studexhi,zidanke,davidcc19880820,BeastWolf_zhang,aguzpow,musclebigpup,gaysiansub,underdaddy63530,keyimo1,BAIWU_99,HengYu1205,zippoo13,wx_soco_man,jeffreyzhan1,DoggyDober,dd779593881,Chao77128403,MasterBBaker,Villanuevo075,inspiredPeng"

const seen = new Set();
const unique = [];
const removed = [];

str.split(",").forEach(name => {
    if (seen.has(name)) {
        removed.push(name);
    } else {
        seen.add(name);
        unique.push(name);
    }
});

console.log("去重后的字符串:");
console.log(unique.join(","));

console.log("被删除的name:");
console.log(removed);
# python 3.8
import time
import hmac
import hashlib
import base64
import urllib.parse
import sys
import requests
import json
from function import *
from lxml import etree

# 检测时间窗口（秒），默认半小时=1800，可在文件顶部统一修改
WINDOW = 1800


def _dingtalk_url(token: str, secret: str) -> str:
    """构造加签后的钉钉自定义机器人 webhook 地址。"""
    timestamp = str(round(time.time() * 1000))
    string_to_sign = '{}\n{}'.format(timestamp, secret)
    hmac_code = hmac.new(
        secret.encode('utf-8'),
        string_to_sign.encode('utf-8'),
        digestmod=hashlib.sha256).digest()
    sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    return "https://oapi.dingtalk.com/robot/send?access_token={2}&timestamp={0}&sign={1}".format(
        timestamp, sign, token)


def sent_message(
        token: str,
        secret: str,
        text: str,
        title: str,
        picUrl: str,
        messageUrl: str):
    url = _dingtalk_url(token, secret)
    data = {
        "msgtype": "link",
        "link": {
            "text": text,
            "title": title,
            "picUrl": picUrl,
            "messageUrl": messageUrl
        }
    }
    headers = {"Content-Type": "application/json"}
    rsp = requests.post(url=url, data=json.dumps(data), headers=headers)
    print(rsp.json().get('errmsg'))


def sent_markdown(token: str, secret: str, title: str, md_text: str):
    """以 markdown 类型发送（用于列表类消息，如选股 Top N）。"""
    url = _dingtalk_url(token, secret)
    data = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": md_text}
    }
    headers = {"Content-Type": "application/json"}
    rsp = requests.post(url=url, data=json.dumps(data), headers=headers)
    print(rsp.json().get('errmsg'))


if __name__ == "__main__":
    from config import *
    try:
        token = sys.argv[1]
        secret = sys.argv[2]
        try:
            mids = sys.argv[3]
            # mids = mids
            bili_subscribe = bool(mids.strip())  # 空值则跳过 bilibili
        except BaseException:
            bili_subscribe = False
        try:
            book_ids = sys.argv[4]
            fanqie_subscribe = bool(book_ids.strip())  # 空值则跳过番茄
        except BaseException:
            fanqie_subscribe = False
        try:
            stock_watchlist = sys.argv[5]
        except BaseException:
            stock_watchlist = watchlist  # 来自 config import *，本地默认自选股
        stock_subscribe = bool((stock_watchlist or "").strip())  # 空值则跳过选股
        print("log:订阅开关 bili={} fanqie={} stock={} ; mids长度={} book_ids长度={}".format(
            bili_subscribe, fanqie_subscribe, stock_subscribe,
            len(mids or ""), len(book_ids or "")))
        China_stp = int(time.time())  # action获取的系统时间突然变成了utc+8，原因不明
        # 小刀网线报处理
        datas = get_message()
        try:
            for url, img, info in datas:
                rsp = requests.get(url=url)
                s = etree.HTML(rsp.text)
                title = s.xpath("//h1[@class='article-title']")[0].text
                date = s.xpath("//time")[0].xpath('string(.)')
                timeArray = time.strptime(date + ":00", "%Y-%m-%d %H:%M:%S")
                timestamp = time.mktime(timeArray)
                ac_time = China_stp - timestamp + 28800
                # 默认时间频率为两小时，可在文件顶部 WINDOW 处统一修改。
                if ac_time < WINDOW:
                    sent_message(
                        token=token,
                        secret=secret,
                        text=date + "\n" + info,
                        title=title,
                        picUrl=img,
                        messageUrl=url)
                    print("log:", date, title, info, "\n")
                else:
                    break
        except BaseException:
            print("error \n", rsp.text)
        # bilibili投稿处理
        if bili_subscribe:
            mid_list = mids.split(',')
            for i in mid_list:
                if not i.strip():
                    continue
                try:
                    video_list = get_video(i)
                    for j in video_list:
                        ac_time = China_stp - j['created']
                        if ac_time < WINDOW:
                            import datetime
                            dateArray = datetime.datetime.fromtimestamp(
                                j['created'] + 28800)
                            otherStyleTime = dateArray.strftime("%m-%d %H:%M:%S")
                            sent_message(
                                token=token,
                                secret=secret,
                                text=j['author'] +
                                " " +
                                otherStyleTime +
                                "\n" +
                                j['description'],
                                title=j['title'],
                                picUrl="https:{}".format(
                                    j['pic']),
                                messageUrl="https://www.bilibili.com/video/{}".format(
                                    j['bvid']))
                            print(
                                "log:",
                                j['created'],
                                j['author'],
                                j['title'],
                                "\n")
                        else:
                            break
                except BaseException as e:
                    print("error bilibili:", i, e)
        else:
            pass
        # 番茄小说更新处理
        if fanqie_subscribe:
            for book_id in book_ids.split(','):
                book_id = book_id.strip()
                if not book_id:
                    continue
                try:
                    meta = get_fanqie_meta(book_id)
                    chapters = get_fanqie_chapters(book_id)
                    for ch in chapters:
                        ac_time = China_stp - ch["firstPassTime"]
                        if ac_time < WINDOW:
                            import datetime
                            dateArray = datetime.datetime.fromtimestamp(
                                ch["firstPassTime"] + 28800)
                            otherStyleTime = dateArray.strftime("%m-%d %H:%M")
                            sent_message(
                                token=token,
                                secret=secret,
                                text="{}    更新于 {}".format(
                                    meta["author"], otherStyleTime),
                                title="《{}》{}".format(
                                    meta["book_name"], ch["title"]),
                                picUrl=meta["cover"] or "",
                                messageUrl="https://fanqienovel.com/reader/{}".format(
                                    ch["itemId"]))
                            print(
                                "log:",
                                meta["book_name"],
                                ch["title"],
                                "\n")
                        else:
                            break
                except BaseException:
                    print("error fanqie:", book_id, "\n")
        # 东方财富选股评分推送（每日收盘后）
        if stock_subscribe:
            try:
                from stock import get_stock_ranked, format_markdown
                codes = [c for c in stock_watchlist.split(',') if c.strip()]
                print("log:开始选股评分，候选数：", len(codes))
                ranked = get_stock_ranked(codes, top_n=10)
                md_text = format_markdown(ranked)
                sent_markdown(token, secret, "📈 每日选股Top{}".format(len(ranked)), md_text)
                print("log:选股推送完成，共推送{}只".format(len(ranked)))
            except BaseException as e:
                print("error stock push:", e)
    except BaseException as e:
        import traceback
        print('secret loss / 顶层异常:', e)
        traceback.print_exc()

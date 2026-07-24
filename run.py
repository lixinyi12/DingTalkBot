# python 3.8
import time
import sys
import requests
from lxml import etree

from common.dingtalk import sent_message, sent_markdown
from common.x6d import get_message
from bilibili import get_video
from fanqie import get_fanqie_meta, get_fanqie_chapters

# 检测时间窗口（秒），默认半小时=1800，可在文件顶部统一修改
WINDOW = 1800


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
        # 选股只在「显式传了第5个参数」时跑（即 Stock_daily 的 5 参数调用），
        # 这样 DingTalk_misson 的 4 参数 cron 不会每 30 分钟误触发选股。
        if len(sys.argv) > 5:
            stock_watchlist = (sys.argv[5] or "").strip() or watchlist  # secret 留空则用 config 兜底
        else:
            stock_watchlist = ""  # 未传第5参数(含 DingTalk_misson 4参数) -> 不跑
        stock_subscribe = bool(stock_watchlist.strip())
        print("log:argv参数数={}; 开关 bili={} fanqie={} stock={}".format(
            len(sys.argv) - 1, bili_subscribe, fanqie_subscribe, stock_subscribe))
        China_stp = int(time.time())  # action获取的系统时间突然变成了utc+8，原因不明
        # 小刀网线报处理
        datas = get_message()
        try:
            for url, img, info in datas:
                # 502 时重试最多5次
                delay = 3
                for attempt in range(5):
                    rsp = requests.get(url=url)
                    if rsp.status_code == 200:
                        break
                    if attempt == 4:
                        raise Exception("x6d[{}] 重试耗尽 status={}".format(url, rsp.status_code))
                    print("x6d[{}] status={} ({}s后重试, {}/{})".format(url, rsp.status_code, delay, attempt + 1, 5))
                    time.sleep(delay)
                    delay = min(delay * 2, 60)
                s = etree.HTML(rsp.text)
                title = s.xpath("//h1[@class='article-title']")[0].text
                date = s.xpath("//time")[0].xpath('string(.)')
                timeArray = time.strptime(date + ":00", "%Y-%m-%d %H:%M:%S")
                timestamp = time.mktime(timeArray)
                ac_time = China_stp - timestamp + 28800
                # 默认时间频率为两小时，可在文件顶部 WINDOW 处统一修改。
                if ac_time < WINDOW + 900:
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
        except BaseException as e:
            detail = ""
            try:
                rsp  # noqa
                status = getattr(rsp, 'status_code', '?')
                detail = " status={} body={}".format(status, rsp.text[:200])
            except BaseException:
                detail = " (响应不可用)"
            print("error x6d[{}]:{}{}".format(url, e, detail))
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

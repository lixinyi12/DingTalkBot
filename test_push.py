# -*- coding: utf-8 -*-
"""本地真实推送测试：强制推送每本书的「最新一章」到钉钉。

用于验证 token / secret / 签名 / 推送链路是否打通，不受 run.py 的 2 小时窗口限制。
每本书会发送一条卡片，钉钉返回的 errmsg 会直接打印（成功为 "ok"）。

运行（PowerShell / Git Bash 均可，不需要传空参数）：
    python test_push.py <token> <secret> <bookId1,bookId2,...>
例如：
    python test_push.py 33216f1daa... SEC39d0b86fe... 7342487397726161944
"""
import datetime
import sys

from fanqie import get_fanqie_chapters, get_fanqie_meta
from common.dingtalk import sent_message


def main():
    if len(sys.argv) < 4:
        print("用法: python test_push.py <token> <secret> <bookId1,bookId2,...>")
        sys.exit(1)

    token, secret, raw_book_ids = sys.argv[1], sys.argv[2], sys.argv[3]
    for book_id in raw_book_ids.split(','):
        book_id = book_id.strip()
        if not book_id:
            continue
        meta = get_fanqie_meta(book_id)
        chapters = get_fanqie_chapters(book_id)
        if not chapters:
            print("未取到章节，跳过：", book_id)
            continue
        ch = chapters[0]  # 最新一章（已按发布时间降序）
        other_time = datetime.datetime.fromtimestamp(
            ch["firstPassTime"] + 28800).strftime("%m-%d %H:%M")
        print(">> 推送最新一章：{} {}".format(meta["book_name"], ch["title"]))
        sent_message(
            token=token,
            secret=secret,
            text="{}    更新于 {}    [测试]".format(meta["author"], other_time),
            title="《{}》{}".format(meta["book_name"], ch["title"]),
            picUrl=meta["cover"] or "",
            messageUrl="https://fanqienovel.com/reader/{}".format(ch["itemId"]))


if __name__ == "__main__":
    main()

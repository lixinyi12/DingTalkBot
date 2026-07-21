# -*- coding: utf-8 -*-
"""番茄小说抓取与解析的本地自测脚本。

运行：python test_fanqie.py [bookId]
不传 bookId 时默认用《十日终焉》的 bookId 做示范。
仅验证 get_fanqie_meta / get_fanqie_chapters 的抓取与解析，
不会调用 sent_message，因此不会向钉钉发送任何消息。
"""
import sys
from function import get_fanqie_meta, get_fanqie_chapters


def main():
    book_id = sys.argv[1] if len(sys.argv) > 1 else "7143038691944959011"

    print("== get_fanqie_meta ==")
    meta = get_fanqie_meta(book_id)
    print(meta)
    assert meta["book_name"], "未解析到书名"
    assert meta["author"], "未解析到作者"

    print("\n== get_fanqie_chapters ==")
    chapters = get_fanqie_chapters(book_id)
    print("章节总数：", len(chapters))
    assert chapters, "章节列表为空"
    print("最新 3 章：")
    for ch in chapters[:3]:
        print(" ", ch)

    first = chapters[0]
    assert first["itemId"], "章节缺少 itemId"
    assert first["title"], "章节缺少 title"
    assert isinstance(first["firstPassTime"], int), "firstPassTime 不是整数"
    # 按发布时间降序：第一条应为最新
    assert chapters[0]["firstPassTime"] >= chapters[-1]["firstPassTime"], "未按时间降序"

    print("\n示例卡片字段：")
    print("  title    : 《{}》{}".format(meta["book_name"], first["title"]))
    cover = meta["cover"]
    print("  cover    :", (cover[:60] + "...") if len(cover) > 60 else cover)
    print("  readerUrl: https://fanqienovel.com/reader/{}".format(first["itemId"]))

    print("\n全部断言通过")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""番茄小说书籍元信息与章节列表抓取。"""
import re
import json
import requests


# 获取番茄小说书籍元信息（书名、作者、封面）
def _extract_json_field(html: str, field: str):
    """从书页内嵌 JSON 中提取单个字段值，正确处理 \\u002F 等转义。"""
    match = re.search(r'"' + field + r'":"((?:[^"\\]|\\.)*)"', html)
    if not match:
        return ""
    return json.loads('"' + match.group(1) + '"')


def get_fanqie_meta(book_id: str):
    url = "https://fanqienovel.com/page/{}".format(book_id)
    rsp = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        timeout=20)
    print("log:番茄书页状态码：", rsp.status_code)
    html = rsp.text
    return {
        "book_name": _extract_json_field(html, "bookName"),
        "author": _extract_json_field(html, "author"),
        "cover": _extract_json_field(html, "thumbUrl"),
    }


# 获取番茄小说章节列表（按发布时间降序：新->旧），每章含 itemId/title/firstPassTime
def get_fanqie_chapters(book_id: str):
    url = "https://fanqienovel.com/api/reader/directory/detail?bookId={}".format(
        book_id)
    rsp = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        timeout=20)
    print("log:番茄目录状态码：", rsp.status_code)
    data = rsp.json()
    if data.get("code") != 0:
        print("log:番茄目录接口异常：", data.get("message"))
        return []
    chapters = []
    for volume in data.get("data", {}).get("chapterListWithVolume", []):
        for chapter in volume:
            first_pass = chapter.get("firstPassTime")
            if not first_pass:
                continue
            chapters.append({
                "itemId": chapter.get("itemId"),
                "title": chapter.get("title"),
                "firstPassTime": int(first_pass),
            })
    chapters.sort(key=lambda c: c["firstPassTime"], reverse=True)
    return chapters

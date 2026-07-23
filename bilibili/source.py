# -*- coding: utf-8 -*-
"""bilibili UP 主投稿抓取。"""
import requests


def get_video(mids: str):
    mid_list = mids.split(',')
    for i in mid_list:
        url = 'https://api.bilibili.com/x/space/arc/search?mid={}&ps=30&tid=0&pn=1&keyword=&order=pubdate&jsonp=jsonp'.format(
            i)
        rsp = requests.get(url)
        datas = rsp.json()['data']['list']['vlist']
        return datas

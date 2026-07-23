# python 3.8
"""钉钉自定义机器人推送工具：加签 webhook 构造 + link/markdown 消息发送。"""
import time
import hmac
import hashlib
import base64
import urllib.parse
import requests
import json


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

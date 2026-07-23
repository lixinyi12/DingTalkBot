# -*- coding: utf-8 -*-
"""东方财富选股评分本地自测脚本。

运行：python test_stock.py
默认对一小撮示范代码跑 取数+打分，并校验结果形状与分数范围。
不会调用 sent_message，因此不会向钉钉发送任何消息。
"""
from stock import get_stock_ranked, format_markdown, score

# 示范自选股：茅台 / 五粮液 / 平安 / 宁德 / 平安银行
DEMO_CODES = ["600519", "000858", "601318", "300750", "000001"]


def main():
    print("== score 单元：空指标应得 0 分且不崩 ==")
    total_empty, _ = score({})
    assert total_empty == 0, "空指标应得0分，实际 {}".format(total_empty)

    print("\n== get_stock_ranked (取数+打分+排序) ==")
    ranked = get_stock_ranked(DEMO_CODES, top_n=10)
    assert ranked, "评分结果为空（可能全部取数失败，检查网络/efinance 是否装好）"
    for r in ranked:
        assert 0 <= r["total"] <= 100, "总分越界: {}".format(r["total"])
        assert "breakdown" in r, "缺少分项明细"
        print("  {} {}: {}分  {}".format(r["code"], r.get("name"), r["total"], r["breakdown"]))
    # 应按总分降序
    totals = [r["total"] for r in ranked]
    assert totals == sorted(totals, reverse=True), "未按总分降序"

    print("\n== format_markdown 预览（前 500 字）==")
    md = format_markdown(ranked)
    print(md[:500])

    print("\n全部断言通过")


if __name__ == "__main__":
    main()

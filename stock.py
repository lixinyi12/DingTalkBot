# -*- coding: utf-8 -*-
"""东方财富股票多维度评分选股（基于 efinance 封装东财数据）。

评分体系（总分 100）：
    基本面 35 = ROE(15) + 归母净利同比(10) + 营收同比(10)
    资金面 30 = 主力净流入占比(20) + 近5日连续净流入(10)
    估值面 20 = PE(10) + PB(10)              # V1 用绝对档位，省去历史分位数
    技术面 15 = 60日均线趋势(8) + RSI14(7)

数据源说明：
    - 主力净流入占比 = 主力净流入额 / 成交额（efinance get_history_bill 已算好百分比）
    - ROE 取自 get_all_company_performance 的“净资产收益率”（注意：季报口径，
      可能是 YTD，阈值若普遍打不满请在下方常量处下调）
    - PE/PB 取自 get_base_info；负值（亏损）按 0 分处理
    - 2025/4 起东财对 IP 限流，故每只股票每次请求间隔 REQUEST_INTERVAL 秒
"""
import time
import datetime
import efinance as ef

# —— 节流（规避东财 IP 限流）——
REQUEST_INTERVAL = 1.2  # 每次请求间隔(秒)

# —— 评分阈值常量（集中放这里方便后续调参）——
# 基本面
ROE_FULL, ROE_MID, ROE_LOW = 15.0, 10.0, 5.0           # ROE %
PROFIT_GROWTH_FULL, PROFIT_GROWTH_MID = 30.0, 15.0      # 归母净利同比 %
REVENUE_GROWTH_FULL, REVENUE_GROWTH_MID = 20.0, 10.0    # 营收同比 %
# 资金面
MAIN_INFLOW_FULL, MAIN_INFLOW_MID = 10.0, 5.0           # 主力净流入占比 %
CONSEC_INFLOW_FULL = 3                                  # 连续净流入天数
# 估值面（绝对档位，V1 简化版）
PE_FULL, PE_MID, PE_HIGH = 15.0, 30.0, 60.0
PB_FULL, PB_MID, PB_HIGH = 2.0, 5.0, 10.0
# 技术面
MA_PERIOD, RSI_PERIOD = 60, 14
RSI_NEUTRAL_LO, RSI_NEUTRAL_HI = 30.0, 50.0             # 30~50 中性偏强


def _normalize_code(code):
    """统一为 efinance 使用的 6 位代码（去掉 sh/sz/bj 前缀）。"""
    code = str(code).strip().lower()
    for prefix in ('sh', 'sz', 'bj'):
        if code.startswith(prefix):
            code = code[len(prefix):]
            break
    return code.strip()


def _to_float(v):
    """安全转 float，None/空/NaN/异常字符串返回 None。"""
    try:
        if v is None:
            return None
        import math
        f = float(v)
        if math.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _rsi(closes, period=RSI_PERIOD):
    """简单 RSI（用最近 period 个交易日的涨跌）。数据不足返回 None。"""
    if len(closes) < period + 1:
        return None
    window = closes[-(period + 1):]
    gains, losses = [], []
    for i in range(1, len(window)):
        d = window[i] - window[i - 1]
        gains.append(d if d > 0 else 0.0)
        losses.append(-d if d < 0 else 0.0)
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 2)


def _fetch_fundamentals(codes):
    """批量取基本面：营收同比、净利同比、ROE。
    get_all_company_performance 一次返回全市场最新季报，再过滤候选池。"""
    out = {}
    if not codes:
        return out
    try:
        df = ef.stock.get_all_company_performance()
        df = df[df['股票代码'].astype(str).isin(codes)]
        for _, row in df.iterrows():
            out[str(row['股票代码'])] = {
                'revenue_yoy': _to_float(row.get('营业收入同比增长')),
                'profit_yoy': _to_float(row.get('净利润同比增长')),
                'roe': _to_float(row.get('净资产收益率')),
            }
        print("log:基本面取到 {}/{}".format(len(out), len(codes)))
    except BaseException as e:
        print("error fundamentals:", e)
    return out


def _fetch_valuation(codes):
    """批量取估值：PE、PB、股票名称。"""
    out = {}
    if not codes:
        return out
    try:
        df = ef.stock.get_base_info(codes)
        for _, row in df.iterrows():
            out[str(row['股票代码'])] = {
                'pe': _to_float(row.get('市盈率(动)')),
                'pb': _to_float(row.get('市净率')),
                'name': row.get('股票名称'),
            }
        print("log:估值取到 {}/{}".format(len(out), len(codes)))
    except BaseException as e:
        print("error valuation:", e)
    return out


def _fetch_capital(code):
    """取资金面：当日主力净流入占比 + 近5日连续净流入天数。"""
    try:
        df = ef.stock.get_history_bill(code)
        if df is None or len(df) == 0:
            return {}
        df = df.sort_values(by='日期')  # 升序，便于取最近 N 日
        last = df.iloc[-1]
        main_pct = _to_float(last.get('主力净流入占比'))
        # 从最近一日往前数，连续净流入天数
        consec = 0
        for amt in reversed(df.tail(5)['主力净流入'].tolist()):
            f = _to_float(amt)
            if f is not None and f > 0:
                consec += 1
            else:
                break
        return {'main_inflow_pct': main_pct, 'consec_inflow': consec}
    except BaseException as e:
        print("error capital:", code, e)
        return {}


def _fetch_technical(code):
    """取技术面：收盘价、是否站上60日均线、均线方向、RSI14、涨跌幅。"""
    try:
        beg = (datetime.date.today() - datetime.timedelta(days=200)).strftime('%Y%m%d')
        df = ef.stock.get_quote_history(code, beg=beg, klt=101, fqt=1)
        if df is None or len(df) == 0:
            return {}
        closes = [_to_float(x) for x in df['收盘'].tolist()]
        closes = [c for c in closes if c is not None]
        if len(closes) < 2:
            return {}
        close = closes[-1]
        result = {'close': close, 'pct_change': _to_float(df.iloc[-1].get('涨跌幅'))}
        if len(closes) >= MA_PERIOD + 1:
            ma_now = sum(closes[-MA_PERIOD:]) / MA_PERIOD
            ma_prev = sum(closes[-MA_PERIOD - 1:-1]) / MA_PERIOD
            result['above_ma60'] = close > ma_now
            result['ma60_up'] = ma_now > ma_prev
        result['rsi'] = _rsi(closes, RSI_PERIOD)
        return result
    except BaseException as e:
        print("error technical:", code, e)
        return {}


def score(ind):
    """四维度打分。ind 为各原始指标 dict，缺失项按 0 分。
    返回 (总分, 分项dict)。"""
    b = {}

    # —— 基本面（35）——
    roe = ind.get('roe')
    if roe is None:
        b['roe'] = 0
    elif roe >= ROE_FULL:
        b['roe'] = 15
    elif roe >= ROE_MID:
        b['roe'] = 10
    elif roe >= ROE_LOW:
        b['roe'] = 5
    else:
        b['roe'] = 0

    pg = ind.get('profit_yoy')
    if pg is None:
        b['profit'] = 0
    elif pg >= PROFIT_GROWTH_FULL:
        b['profit'] = 10
    elif pg >= PROFIT_GROWTH_MID:
        b['profit'] = 6
    elif pg >= 0:
        b['profit'] = 3
    else:
        b['profit'] = 0

    rg = ind.get('revenue_yoy')
    if rg is None:
        b['revenue'] = 0
    elif rg >= REVENUE_GROWTH_FULL:
        b['revenue'] = 10
    elif rg >= REVENUE_GROWTH_MID:
        b['revenue'] = 6
    elif rg >= 0:
        b['revenue'] = 3
    else:
        b['revenue'] = 0

    # —— 资金面（30）——
    mp = ind.get('main_inflow_pct')
    if mp is None:
        b['main_inflow'] = 0
    elif mp >= MAIN_INFLOW_FULL:
        b['main_inflow'] = 20
    elif mp >= MAIN_INFLOW_MID:
        b['main_inflow'] = 14
    elif mp >= 0:
        b['main_inflow'] = 7
    else:
        b['main_inflow'] = 0

    ci = ind.get('consec_inflow') or 0
    if ci >= CONSEC_INFLOW_FULL:
        b['trend'] = 10
    elif ci == 2:
        b['trend'] = 5
    else:
        b['trend'] = 0

    # —— 估值面（20，绝对档位）——
    pe = ind.get('pe')
    if pe is None or pe <= 0:
        b['pe'] = 0          # 负 PE（亏损）或缺失
    elif pe <= PE_FULL:
        b['pe'] = 10
    elif pe <= PE_MID:
        b['pe'] = 6
    elif pe <= PE_HIGH:
        b['pe'] = 3
    else:
        b['pe'] = 0

    pb = ind.get('pb')
    if pb is None or pb <= 0:
        b['pb'] = 0
    elif pb <= PB_FULL:
        b['pb'] = 10
    elif pb <= PB_MID:
        b['pb'] = 6
    elif pb <= PB_HIGH:
        b['pb'] = 3
    else:
        b['pb'] = 0

    # —— 技术面（15）——
    above = ind.get('above_ma60')
    ma_up = ind.get('ma60_up')
    if above and ma_up:
        b['ma60'] = 8
    elif above:
        b['ma60'] = 4
    else:
        b['ma60'] = 0

    rsi = ind.get('rsi')
    if rsi is None:
        b['rsi'] = 0
    elif RSI_NEUTRAL_LO <= rsi <= RSI_NEUTRAL_HI:
        b['rsi'] = 7          # 30~50 中性偏强
    elif RSI_NEUTRAL_HI < rsi <= 70:
        b['rsi'] = 4          # 50~70
    else:
        b['rsi'] = 2          # <30 超卖 或 >70 超买

    return sum(b.values()), b


def get_stock_ranked(codes, top_n=10):
    """主流程：候选池 -> 逐股取4维度 -> 打分 -> 排序 -> 返回 Top N。
    单只取数失败会跳过该股，不影响其余。"""
    # 归一化 + 去重（保序）
    seen = set()
    codes = [_normalize_code(c) for c in codes if str(c).strip()]
    codes = [c for c in codes if not (c in seen or seen.add(c))]
    if not codes:
        print("log:候选池为空")
        return []

    print("log:候选池股票数：", len(codes))
    # 批量取基本面 + 估值（各 1 次调用）
    fund = _fetch_fundamentals(codes)
    time.sleep(REQUEST_INTERVAL)
    val = _fetch_valuation(codes)

    results = []
    for i, code in enumerate(codes, 1):
        try:
            time.sleep(REQUEST_INTERVAL)
            cap = _fetch_capital(code)
            time.sleep(REQUEST_INTERVAL)
            tech = _fetch_technical(code)

            ind = {}
            ind.update(fund.get(code, {}))
            ind.update(val.get(code, {}))
            ind.update(cap)
            ind.update(tech)
            ind['code'] = code

            total, breakdown = score(ind)
            results.append({
                'code': code,
                'name': ind.get('name') or code,
                'total': total,
                'breakdown': breakdown,
                'close': ind.get('close'),
                'pct_change': ind.get('pct_change'),
            })
            print("log: [{}/{}] {} {} 得分 {}".format(i, len(codes), code, ind.get('name', ''), total))
        except BaseException as e:
            print("error stock:", code, e)

    results.sort(key=lambda r: r['total'], reverse=True)
    return results[:top_n]


def format_markdown(ranked):
    """把评分结果格式化为钉钉 markdown 文本（钉钉 md 不支持表格，用列表）。"""
    if not ranked:
        return "今日无符合条件的股票（候选池为空或数据获取失败）"
    today = datetime.date.today().strftime('%Y-%m-%d')
    header = "# 📈 每日选股 Top{}\n> {} 收盘后评分".format(len(ranked), today)
    lines = [header]
    for i, r in enumerate(ranked, 1):
        bd = r['breakdown']
        fund_s = bd.get('roe', 0) + bd.get('profit', 0) + bd.get('revenue', 0)
        cap_s = bd.get('main_inflow', 0) + bd.get('trend', 0)
        val_s = bd.get('pe', 0) + bd.get('pb', 0)
        tech_s = bd.get('ma60', 0) + bd.get('rsi', 0)
        price = ""
        if r.get('close') is not None:
            price = "  现价{}".format(round(r['close'], 2))
            if r.get('pct_change') is not None:
                price += "({}%)".format(round(r['pct_change'], 2))
        lines.append(
            "**{}. {}({})  {}分**{}\n"
            "> 基本{}/资金{}/估值{}/技术{}".format(
                i, r.get('name'), r['code'], r['total'], price,
                fund_s, cap_s, val_s, tech_s))
    return "\n\n".join(lines)

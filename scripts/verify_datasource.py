#!/usr/bin/env python3
"""数据源迁移验证脚本

用法：
  python scripts/verify_datasource.py              # 默认验证 legacy 模式
  python scripts/verify_datasource.py new           # 验证 new 模式
  python scripts/verify_datasource.py shadow        # 验证 shadow 模式（对比新旧源）
  python scripts/verify_datasource.py compare       # 对比新旧源数据一致性

输出：验证结果摘要 + 详细日志
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

# 测试股票池（覆盖不同板块）
TEST_CODES = [
    "600519",   # 沪市主板 - 贵州茅台
    "000001",   # 深市主板 - 平安银行
    "300750",   # 创业板 - 宁德时代
    "688981",   # 科创板 - 中芯国际
    "000858",   # 深市主板 - 五粮液
    "601318",   # 沪市主板 - 中国平安
    "002594",   # 深市中小板 - 比亚迪
    "600036",   # 沪市主板 - 招商银行
]


def test_quote_service(mode: str):
    """测试 QuoteService 在指定模式下的行为"""
    os.environ["DATA_SOURCE_MODE"] = mode
    import importlib
    import config.settings
    importlib.reload(config.settings)

    from data.collector.quote_service import _fetch_batch_quotes

    print(f"\n{'='*60}")
    print(f"测试模式: {mode}")
    print(f"{'='*60}")

    start = time.time()
    result = _fetch_batch_quotes(TEST_CODES)
    elapsed = time.time() - start

    print(f"耗时: {elapsed:.2f}s")
    print(f"成功获取: {len(result)}/{len(TEST_CODES)} 只")

    if not result:
        print("❌ 未获取到任何数据")
        return None

    print(f"\n{'代码':<8} {'名称':<8} {'价格':>10} {'涨跌%':>8} {'PE':>8} {'PB':>8} "
          f"{'市值(亿)':>10} {'换手率%':>8} {'涨停':>10} {'跌停':>10}")
    print("-" * 100)

    for code in TEST_CODES:
        q = result.get(code)
        if not q:
            print(f"{code:<8} {'N/A':<8} {'获取失败':>10}")
            continue
        cap_yi = q.market_cap / 10000 if q.market_cap else 0
        print(f"{q.code:<8} {q.name:<8} {q.price:>10.2f} {q.change_pct:>8.2f} "
              f"{q.pe_ratio:>8.2f} {q.pb_ratio:>8.2f} {cap_yi:>10.0f} "
              f"{q.turnover_rate:>8.2f} {q.limit_up:>10.2f} {q.limit_down:>10.2f}")

    return result


def test_kline(mode: str):
    """测试 K线数据"""
    os.environ["DATA_SOURCE_MODE"] = mode
    import importlib
    import config.settings
    importlib.reload(config.settings)

    from data.collector.http_client import fetch_kline

    print(f"\n{'='*60}")
    print(f"K线测试 ({mode} 模式)")
    print(f"{'='*60}")

    for code in TEST_CODES[:3]:
        start = time.time()
        kline = fetch_kline(code, count=250, period="day")
        elapsed = time.time() - start

        if kline:
            print(f"  {code}: {len(kline['klines_raw'])} 条K线, 耗时 {elapsed:.2f}s")
            latest = kline["klines_raw"][-1]
            print(f"    最新: {latest}")
        else:
            print(f"  {code}: ❌ K线获取失败")


def test_financial(mode: str):
    """测试财务数据"""
    os.environ["DATA_SOURCE_MODE"] = mode
    import importlib
    import config.settings
    importlib.reload(config.settings)

    from data.collector.quote_service import _fetch_financial_data

    print(f"\n{'='*60}")
    print(f"财务数据测试 ({mode} 模式)")
    print(f"{'='*60}")

    for code in TEST_CODES[:3]:
        start = time.time()
        fin = _fetch_financial_data(code)
        elapsed = time.time() - start

        if fin:
            print(f"  {code}: 耗时 {elapsed:.2f}s")
            print(f"    总股本={fin.get('total_shares', 0):.0f} "
                  f"EPS={fin.get('eps', 0):.2f} "
                  f"52周高={fin.get('high_52w', 0):.2f} "
                  f"52周低={fin.get('low_52w', 0):.2f}")
        else:
            print(f"  {code}: ❌ 财务数据获取失败")


def compare_sources():
    """对比新旧数据源一致性"""
    from data.collector.quote_service import _fetch_batch_quotes_push2, _fetch_batch_quotes_mootdx
    from data.collector.shadow_validator import validate_quote_consistency

    print(f"\n{'='*60}")
    print("新旧数据源对比")
    print(f"{'='*60}")

    # 获取旧源数据
    old_result = _fetch_batch_quotes_push2(TEST_CODES)
    # 获取新源数据
    new_result = _fetch_batch_quotes_mootdx(TEST_CODES)

    if not old_result:
        print("❌ 旧数据源获取失败")
        return
    if not new_result:
        print("❌ 新数据源获取失败")
        return

    total = 0
    match = 0
    diff_codes = []

    for code in TEST_CODES:
        if code not in old_result or code not in new_result:
            print(f"  {code}: 一侧无数据")
            continue

        total += 1
        old_dict = old_result[code].__dict__
        new_dict = new_result[code].__dict__
        diffs = validate_quote_consistency(code, old_dict, new_dict)

        if not diffs:
            match += 1
            print(f"  {code} ✅ 一致 (价格: 旧={old_dict.get('price'):.2f} 新={new_dict.get('price'):.2f})")
        else:
            diff_codes.append(code)
            print(f"  {code} ⚠️  {len(diffs)} 项差异:")
            for d in diffs:
                print(f"    {d['field']}: 旧={d.get('old')} 新={d.get('new')}")

    print(f"\n一致性: {match}/{total} ({match/max(total,1)*100:.1f}%)")
    if diff_codes:
        print(f"有差异的股票: {', '.join(diff_codes)}")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "legacy"

    print(f"数据源迁移验证 — 模式: {mode}")
    print(f"测试股票: {', '.join(TEST_CODES)}")

    if mode == "compare":
        compare_sources()
    else:
        test_quote_service(mode)
        test_kline(mode)
        test_financial(mode)

    # 恢复默认
    os.environ["DATA_SOURCE_MODE"] = "legacy"
    print("\n✅ 验证完成")


if __name__ == "__main__":
    main()

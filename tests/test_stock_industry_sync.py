import pandas as pd


def test_sync_stock_industries_fills_missing_stock_info_with_batch_fetcher(tmp_path):
    from data.storage.storage import DataStorage
    from data.sync.stock_industry import sync_stock_industries

    storage = DataStorage(db_url=f"sqlite:///{tmp_path / 'test.db'}")
    storage.init_db()
    storage.save_stock_info(
        pd.DataFrame(
            [
                {"code": "600519", "name": "贵州茅台", "industry": "", "list_date": "2001-08-27"},
                {"code": "000001", "name": "平安银行", "industry": "银行", "list_date": "1991-04-03"},
            ]
        )
    )
    calls = []

    def fake_fetch(codes):
        calls.append(list(codes))
        return {"600519": {"industry": "白酒", "sector": "食品饮料"}}

    summary = sync_stock_industries(storage=storage, fetch_industry_fn=fake_fetch)

    assert calls == [["600519"]]
    assert summary.target_count == 1
    assert summary.filled_count == 1
    assert summary.updated_count == 1
    row = storage.get_stock_list()
    assert row[row["code"] == "600519"].iloc[0]["industry"] == "白酒"


def test_sync_stock_industries_dry_run_does_not_write_database(tmp_path):
    from data.storage.storage import DataStorage
    from data.sync.stock_industry import sync_stock_industries

    storage = DataStorage(db_url=f"sqlite:///{tmp_path / 'test.db'}")
    storage.init_db()
    storage.save_stock_info(
        pd.DataFrame(
            [
                {"code": "600519", "name": "贵州茅台", "industry": "", "list_date": "2001-08-27"},
                {"code": "000001", "name": "平安银行", "industry": "银行", "list_date": "1991-04-03"},
            ]
        )
    )

    summary = sync_stock_industries(
        storage=storage,
        codes=["sh600519", "000001"],
        fetch_industry_fn=lambda codes: {"600519": {"industry": "白酒"}},
        dry_run=True,
    )

    assert summary.target_count == 1
    assert summary.filled_count == 1
    assert summary.updated_count == 0
    row = storage.get_stock_list()
    assert row[row["code"] == "600519"].iloc[0]["industry"] == ""


def test_sync_stock_industries_batches_external_fetches(tmp_path):
    from data.storage.storage import DataStorage
    from data.sync.stock_industry import sync_stock_industries

    storage = DataStorage(db_url=f"sqlite:///{tmp_path / 'test.db'}")
    storage.init_db()
    storage.save_stock_info(
        pd.DataFrame(
            [
                {"code": "600519", "name": "贵州茅台", "industry": "", "list_date": ""},
                {"code": "000001", "name": "平安银行", "industry": "", "list_date": ""},
                {"code": "300750", "name": "宁德时代", "industry": "", "list_date": ""},
            ]
        )
    )
    calls = []

    def fake_fetch(codes):
        calls.append(list(codes))
        return {code: {"industry": f"行业{code}"} for code in codes}

    summary = sync_stock_industries(storage=storage, fetch_industry_fn=fake_fetch, batch_size=2)

    assert calls == [["600519", "000001"], ["300750"]]
    assert summary.target_count == 3
    assert summary.filled_count == 3
    assert summary.updated_count == 3


def test_stock_industry_cli_parse_codes_accepts_repeated_and_comma_separated_values():
    from scripts.sync_stock_industry import parse_codes

    assert parse_codes(["600519,000001", " 300750 "]) == [
        "600519",
        "000001",
        "300750",
    ]

import pandas as pd


def _daily_frame(close: float = 10.0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": "2026-05-26",
                "open": close - 0.2,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1000,
                "amount": 10000,
            },
            {
                "date": "2026-05-27",
                "open": close,
                "high": close + 1.0,
                "low": close - 0.3,
                "close": close + 0.4,
                "volume": 1200,
                "amount": 12480,
            },
        ]
    )


class FakeAdapter:
    def __init__(self, frames=None, errors=None):
        self.frames = frames or {}
        self.errors = errors or {}
        self.calls = []

    async def get_kline(self, code, frequency=9, start=0, offset=800):
        self.calls.append(
            {"code": code, "frequency": frequency, "start": start, "offset": offset}
        )
        if code in self.errors:
            raise self.errors[code]
        return self.frames.get(code, pd.DataFrame())


class FakeStorage:
    def __init__(self):
        self.saved = []

    def save_stock_daily(self, code, df):
        self.saved.append((code, df.copy()))
        return len(df)


def test_sync_qlib_daily_writes_rows_and_generates_predictions():
    from scripts.sync_qlib_daily import sync_qlib_daily

    adapter = FakeAdapter(
        frames={
            "600519": _daily_frame(100.0),
            "000001": _daily_frame(10.0),
        }
    )
    storage = FakeStorage()
    prediction_calls = []

    def fake_generate_predictions():
        prediction_calls.append(True)
        return type(
            "Summary",
            (),
            {"success": True, "latest_date": "2026-05-27", "total": 2, "message": ""},
        )()

    summary = sync_qlib_daily(
        codes=["600519", "000001"],
        count=2,
        storage=storage,
        adapter=adapter,
        generate_predictions_fn=fake_generate_predictions,
        generate_predictions_cache=True,
        min_success=2,
    )

    assert summary.success is True
    assert summary.success_count == 2
    assert summary.fail_count == 0
    assert summary.prediction_total == 2
    assert prediction_calls == [True]
    assert [call["offset"] for call in adapter.calls] == [2, 2]
    assert [code for code, _ in storage.saved] == ["600519", "000001"]
    assert storage.saved[0][1]["adj_factor"].tolist() == [1.0, 1.0]
    assert summary.items[0].latest_date == "2026-05-27"


def test_sync_qlib_daily_records_failures_and_skips_predictions_below_min_success():
    from scripts.sync_qlib_daily import sync_qlib_daily

    adapter = FakeAdapter(
        frames={"600519": _daily_frame(100.0)},
        errors={"000001": RuntimeError("remote closed")},
    )
    storage = FakeStorage()
    prediction_calls = []

    summary = sync_qlib_daily(
        codes=["600519", "000001"],
        storage=storage,
        adapter=adapter,
        generate_predictions_fn=lambda: prediction_calls.append(True),
        generate_predictions_cache=True,
        min_success=2,
    )

    assert summary.success is False
    assert summary.success_count == 1
    assert summary.fail_count == 1
    assert prediction_calls == []
    assert summary.items[1].success is False
    assert "remote closed" in summary.items[1].error


def test_parse_codes_accepts_repeated_and_comma_separated_values():
    from scripts.sync_qlib_daily import parse_codes

    assert parse_codes(["600519,000001", " 300750 "]) == [
        "600519",
        "000001",
        "300750",
    ]

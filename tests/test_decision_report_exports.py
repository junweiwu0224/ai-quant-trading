from __future__ import annotations

import json

from decision.report_export import report_to_json, report_to_markdown, report_to_pdf


def _report() -> dict:
    return {
        "id": "report-1",
        "report_type": "preview",
        "report_hash": "abc123",
        "body": {
            "report_type": "preview",
            "portfolio_id": "portfolio-1",
            "portfolio_version_id": "version-1",
            "input_hash": "input-1",
            "source": "local_quant_db",
            "quality_status": "ok",
            "data_quality": {"coverage_pct": 100, "provider": "fixture"},
            "decisions": [{"symbol": "600519", "action": "hold", "score": 1.2, "valid": True, "confirmed": True, "reason_codes": ["stable"]}],
        },
    }


def test_exports_are_read_only_and_include_frozen_hashes() -> None:
    report = _report()
    payload = json.loads(report_to_json(report))
    markdown = report_to_markdown(report).decode("utf-8")
    pdf = report_to_pdf(report)

    assert payload["report_hash"] == "abc123"
    assert "input-1" in markdown
    assert "600519" in markdown
    assert pdf.startswith(b"%PDF-")
    assert b"/STSong-Light" in pdf

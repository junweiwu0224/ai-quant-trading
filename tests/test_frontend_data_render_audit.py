import json
from pathlib import Path

from scripts.frontend_data_render_audit import (
    RenderRisk,
    build_report,
    main,
    scan_js_text,
    scan_static_tree,
)


def test_scan_js_text_flags_raw_tofixed_and_innerhtml():
    text = """
    priceCell.textContent = '¥' + q.price.toFixed(2);
    panel.innerHTML = `<td>${payload.value}</td>`;
    safe.textContent = DisplayFormat.money(payload.value);
    """

    risks = scan_js_text(text, Path("dashboard/static/sample.js"))
    keys = {(risk.kind, risk.severity) for risk in risks}

    assert ("raw_to_fixed", "high") in keys
    assert ("dynamic_inner_html", "medium") in keys
    assert all(isinstance(risk, RenderRisk) for risk in risks)


def test_scan_js_text_flags_number_placeholder_and_nan_check():
    text = """
    const price = Number(row.price);
    const label = row.name || '--';
    if (isNaN(price)) return;
    """

    risks = scan_js_text(text, Path("dashboard/static/sample.js"))
    keys = {(risk.kind, risk.severity) for risk in risks}

    assert ("raw_number_constructor", "medium") in keys
    assert ("fallback_or_placeholder", "medium") in keys
    assert ("direct_nan_check", "low") in keys


def test_scan_js_text_ignores_comments_and_empty_lines():
    text = """
    // value.toFixed(2)
    * value.toFixed(2)

    const value = DisplayFormat.percent(row.ratio);
    """

    assert scan_js_text(text, Path("dashboard/static/sample.js")) == []


def test_scan_static_tree_returns_sorted_risks(tmp_path):
    first = tmp_path / "b.js"
    second = tmp_path / "a.js"
    ignored = tmp_path / "node_modules" / "ignored.js"
    first.write_text("x.innerHTML = `<span>${value}</span>`;", encoding="utf-8")
    second.write_text("y.textContent = z.toFixed(2);", encoding="utf-8")
    ignored.parent.mkdir()
    ignored.write_text("ignored.toFixed(2);", encoding="utf-8")

    risks = scan_static_tree(tmp_path)

    assert [risk.file for risk in risks] == ["a.js", "b.js"]


def test_build_report_counts_risks_by_kind_and_severity(tmp_path):
    source = tmp_path / "sample.js"
    source.write_text(
        "\n".join(
            [
                "a.textContent = row.price.toFixed(2);",
                "b.textContent = row.value || \"--\";",
                "if (isNaN(row.value)) return;",
            ]
        ),
        encoding="utf-8",
    )

    report = build_report(tmp_path)

    assert report["kind"] == "frontend_static"
    assert report["root"] == tmp_path.as_posix()
    assert report["risk_count"] == 3
    assert report["by_kind"] == {
        "direct_nan_check": 1,
        "fallback_or_placeholder": 1,
        "raw_to_fixed": 1,
    }
    assert report["by_severity"] == {"high": 1, "low": 1, "medium": 1}
    assert [risk["file"] for risk in report["risks"]] == ["sample.js", "sample.js", "sample.js"]


def test_main_writes_json_report(tmp_path):
    source = tmp_path / "sample.js"
    output = tmp_path / "report.json"
    source.write_text("a.textContent = row.price.toFixed(2);", encoding="utf-8")

    assert main(["--root", str(tmp_path), "--output", str(output)]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["risk_count"] == 1
    assert report["by_severity"] == {"high": 1}


def test_render_risk_to_dict_is_json_serializable():
    risk = RenderRisk(
        file="dashboard/static/sample.js",
        line=7,
        kind="raw_to_fixed",
        severity="high",
        snippet="value.toFixed(2);",
    )

    assert json.loads(json.dumps(risk.to_dict())) == {
        "file": "dashboard/static/sample.js",
        "line": 7,
        "kind": "raw_to_fixed",
        "severity": "high",
        "snippet": "value.toFixed(2);",
    }

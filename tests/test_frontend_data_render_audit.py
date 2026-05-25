import json
from pathlib import Path

from scripts.frontend_data_render_audit import (
    RISK_PATTERNS,
    RenderRisk,
    build_report,
    main,
    scan_js_text,
    scan_static_tree,
)


def test_risk_patterns_registry_includes_dynamic_inner_html():
    assert any(kind == "dynamic_inner_html" for kind, _severity, _pattern in RISK_PATTERNS)


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


def test_scan_js_text_flags_multiline_innerhtml_template_interpolation():
    text = """
    tbody.innerHTML = rows.map((row) => `
      <tr><td>${row.name}</td></tr>
    `).join("");
    """

    risks = scan_js_text(text, Path("dashboard/static/sample.js"))

    assert any(risk.kind == "dynamic_inner_html" for risk in risks)


def test_scan_js_text_flags_innerhtml_append_template_interpolation():
    text = "container.innerHTML += `<span>${value}</span>`;"

    risks = scan_js_text(text, Path("dashboard/static/sample.js"))

    assert any(risk.kind == "dynamic_inner_html" for risk in risks)


def test_scan_js_text_does_not_flag_innerhtml_strict_comparison():
    text = "if (node.innerHTML === `<span>${value}</span>`) {}"

    risks = scan_js_text(text, Path("dashboard/static/sample.js"))

    assert not any(risk.kind == "dynamic_inner_html" for risk in risks)


def test_scan_js_text_does_not_cross_statement_boundary_for_innerhtml():
    text = """
    el.innerHTML = safeHtml;
    const label = `${row.name}`;
    """

    risks = scan_js_text(text, Path("dashboard/static/sample.js"))

    assert not any(risk.kind == "dynamic_inner_html" for risk in risks)


def test_scan_js_text_does_not_cross_asi_boundary_for_innerhtml():
    text = """
    el.innerHTML = safeHtml
    const label = `${row.name}`;
    """

    risks = scan_js_text(text, Path("dashboard/static/sample.js"))

    assert not any(risk.kind == "dynamic_inner_html" for risk in risks)


def test_scan_js_text_flags_innerhtml_template_with_semicolon_before_interpolation():
    text = "panel.innerHTML = `<span>; ${value}</span>`;"

    risks = scan_js_text(text, Path("dashboard/static/sample.js"))

    assert any(risk.kind == "dynamic_inner_html" for risk in risks)


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


def test_scan_static_tree_raises_when_root_is_missing(tmp_path):
    missing = tmp_path / "missing"

    try:
        scan_static_tree(missing)
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("scan_static_tree should fail fast for a missing root")


def test_scan_static_tree_raises_when_root_is_a_file(tmp_path):
    root_file = tmp_path / "sample.js"
    root_file.write_text("value.toFixed(2);", encoding="utf-8")

    try:
        scan_static_tree(root_file)
    except NotADirectoryError as exc:
        assert str(root_file) in str(exc)
    else:
        raise AssertionError("scan_static_tree should fail fast for a file root")


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

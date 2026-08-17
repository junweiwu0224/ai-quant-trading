"""Deterministic export formats for immutable decision reports.

Exports are projections of a stored report.  They never fetch market data,
recompute a decision, or mutate the audit record.
"""

from __future__ import annotations

import html
import io
import json
from collections.abc import Mapping
from typing import Any


_PDF_FONT_NAME = "STSong-Light"


def _register_cjk_font() -> str:
    """Register ReportLab's built-in CJK font for Chinese report labels."""

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    try:
        pdfmetrics.getFont(_PDF_FONT_NAME)
    except KeyError:
        pdfmetrics.registerFont(UnicodeCIDFont(_PDF_FONT_NAME))
    return _PDF_FONT_NAME


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value)


def report_to_json(report: Mapping[str, Any]) -> bytes:
    """Serialize the stored report envelope without adding runtime fields."""

    return json.dumps(dict(report), ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")


def report_to_markdown(report: Mapping[str, Any]) -> bytes:
    """Render a human-readable evidence export from the frozen report body."""

    body = report.get("body") if isinstance(report.get("body"), Mapping) else {}
    decisions = body.get("decisions") if isinstance(body.get("decisions"), list) else []
    quality = body.get("data_quality") if isinstance(body.get("data_quality"), Mapping) else {}
    validation = body.get("validation") if isinstance(body.get("validation"), Mapping) else {}
    eligibility = body.get("eligibility") if isinstance(body.get("eligibility"), Mapping) else {}
    capabilities = body.get("market_capabilities") if isinstance(body.get("market_capabilities"), Mapping) else {}
    strategy_weights = body.get("strategy_weights") if isinstance(body.get("strategy_weights"), list) else []
    evidence = body.get("evidence") if isinstance(body.get("evidence"), Mapping) else {}
    commentary = report.get("ai_commentary") if isinstance(report.get("ai_commentary"), list) else []
    deliveries = report.get("delivery_attempts") if isinstance(report.get("delivery_attempts"), list) else []
    lines = [
        "# AI Quant 决策报告",
        "",
        f"- 报告 ID：{_text(report.get('id'))}",
        f"- 报告类型：{_text(body.get('report_type') or report.get('report_type'))}",
        f"- 组合：{_text(body.get('portfolio_id'))}",
        f"- 组合版本：{_text(body.get('portfolio_version_id'))}",
        f"- 输入 hash：`{_text(body.get('input_hash'))}`",
        f"- 报告 hash：`{_text(report.get('report_hash'))}`",
        f"- 质量状态：{_text(body.get('quality_status'))}",
        f"- 市场：{_text(body.get('market'))}",
        f"- 验证状态：{_text(validation.get('status') or 'not_run')}",
        f"- 自动推送资格：{_text(eligibility.get('status') or 'not_checked')}",
        "",
        "## 数据质量",
        "",
    ]
    if quality:
        lines.extend(f"- {key}：{_text(value)}" for key, value in quality.items())
    else:
        lines.append("- 未提供数据质量 envelope")
    lines.extend(["", "## 市场能力", ""])
    if capabilities:
        for key in ("display_name", "timezone", "calendar_name", "calendar_source", "daily_granularities", "intraday_granularities", "automatic_push_supported", "providers"):
            if key in capabilities:
                lines.append(f"- {key}：{_text(capabilities[key])}")
    else:
        lines.append("- 未提供市场能力 envelope")
    lines.extend(["", "## 策略与证据", ""])
    lines.append(f"- 策略权重：{_text(strategy_weights)}")
    lines.append(f"- 证据摘要：{_text({key: value for key, value in evidence.items() if key != 'snapshot_id'})}")
    if validation:
        lines.append(f"- 验证原因：{_text((validation.get('result') or {}).get('reasons') if isinstance(validation.get('result'), Mapping) else [])}")
    lines.extend(["", "## 决策明细", "", "| 标的 | 动作 | 分数 | 有效 | 确认 | 原因 |", "|---|---|---:|---|---|---|"])
    for decision in decisions:
        if not isinstance(decision, Mapping):
            continue
        reasons = "、".join(str(item) for item in (decision.get("reason_codes") or []))
        lines.append(
            "| {symbol} | {action} | {score} | {valid} | {confirmed} | {reasons} |".format(
                symbol=_text(decision.get("symbol")),
                action=_text(decision.get("action")),
                score=_text(decision.get("score")) or "—",
                valid="是" if decision.get("valid") else "否",
                confirmed="是" if decision.get("confirmed") else "否",
                reasons=reasons.replace("|", "\\|"),
            )
        )
    if not decisions:
        lines.append("| — | 无决策 | — | — | — | 没有可展示的决策 |")
    lines.extend(["", "## AI 解释与投递历史", ""])
    lines.append(f"- AI 解释状态：{_text(report.get('ai_commentary_status') or ('available' if commentary else 'not_available'))}")
    lines.append(f"- AI 补充件：{_text(commentary)}")
    lines.append(f"- 投递尝试：{_text(deliveries)}")
    lines.extend(["", "---", "", "本导出由已冻结的决策报告生成，不代表真实交易建议。"])
    return ("\n".join(lines) + "\n").encode("utf-8")


def report_to_pdf(report: Mapping[str, Any]) -> bytes:
    """Create a compact PDF evidence export without external network access."""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    body = report.get("body") if isinstance(report.get("body"), Mapping) else {}
    decisions = body.get("decisions") if isinstance(body.get("decisions"), list) else []
    buffer = io.BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    font_name = _register_cjk_font()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("DecisionTitle", parent=styles["Title"], fontName=font_name, fontSize=16, leading=20, spaceAfter=8)
    body_style = ParagraphStyle("DecisionBody", parent=styles["BodyText"], fontName=font_name, fontSize=8, leading=11)
    small = ParagraphStyle("DecisionSmall", parent=body_style, fontSize=7, leading=9)
    heading = ParagraphStyle("DecisionHeading", parent=styles["Heading2"], fontName=font_name)
    story = [
        Paragraph("AI Quant 决策报告", title),
        Paragraph(html.escape(f"报告 hash：{_text(report.get('report_hash'))}"), small),
        Spacer(1, 5 * mm),
    ]
    metadata = [
        ["报告类型", _text(body.get("report_type") or report.get("report_type")), "质量状态", _text(body.get("quality_status"))],
        ["组合", _text(body.get("portfolio_id")), "版本", _text(body.get("portfolio_version_id"))],
        ["输入 hash", _text(body.get("input_hash")), "来源", _text(body.get("source"))],
        ["市场", _text(body.get("market")), "验证", _text((body.get("validation") or {}).get("status") if isinstance(body.get("validation"), Mapping) else "not_run")],
        ["AI 解释", _text(report.get("ai_commentary_status") or "not_available"), "投递尝试", _text(len(report.get("delivery_attempts") or []))],
    ]
    metadata_table = Table(metadata, colWidths=[23 * mm, 67 * mm, 23 * mm, 67 * mm])
    metadata_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d5d5d5")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f3f3")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f3f3f3")),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.extend([metadata_table, Spacer(1, 6 * mm), Paragraph("决策明细", heading)])
    rows = [["标的", "动作", "分数", "有效", "确认", "原因"]]
    for decision in decisions:
        if not isinstance(decision, Mapping):
            continue
        rows.append([
            _text(decision.get("symbol")),
            _text(decision.get("action")),
            _text(decision.get("score")) or "—",
            "是" if decision.get("valid") else "否",
            "是" if decision.get("confirmed") else "否",
            _text(decision.get("reason_codes")),
        ])
    if len(rows) == 1:
        rows.append(["—", "无决策", "—", "—", "—", "没有可展示的决策"])
    decisions_table = Table(rows, colWidths=[25 * mm, 32 * mm, 20 * mm, 18 * mm, 18 * mm, 67 * mm], repeatRows=1)
    decisions_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5d6570")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#d5d5d5")),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (-1, -1), font_name),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
    ]))
    story.extend([decisions_table, Spacer(1, 6 * mm), Paragraph("本导出由已冻结的决策报告生成，不代表真实交易建议。", small)])
    document.build(story)
    return buffer.getvalue()


__all__ = ["report_to_json", "report_to_markdown", "report_to_pdf"]

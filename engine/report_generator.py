"""PDF 回测报告生成器"""
import io
from datetime import datetime
from config.datetime_utils import now_beijing, now_beijing_iso, now_beijing_str, today_beijing, today_beijing_compact
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak, HRFlowable,
)
from reportlab.graphics.shapes import Drawing, Line
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


def generate_backtest_report(data: dict[str, Any]) -> bytes:
    """生成回测 PDF 报告，返回 PDF 字节流"""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=20 * mm, bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        'TitleCN', parent=styles['Title'],
        fontName='Helvetica-Bold', fontSize=18, spaceAfter=6 * mm,
    ))
    styles.add(ParagraphStyle(
        'SubTitleCN', parent=styles['Normal'],
        fontName='Helvetica', fontSize=10, textColor=colors.HexColor('#666666'),
        alignment=TA_CENTER, spaceAfter=8 * mm,
    ))
    styles.add(ParagraphStyle(
        'SectionCN', parent=styles['Heading2'],
        fontName='Helvetica-Bold', fontSize=13, spaceBefore=6 * mm, spaceAfter=3 * mm,
        textColor=colors.HexColor('#333333'),
    ))
    styles.add(ParagraphStyle(
        'BodyCN', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9, leading=14,
    ))

    elements = []

    # ── 标题 ──
    elements.append(Paragraph('AI Quant Backtest Report', styles['TitleCN']))
    gen_time = now_beijing().strftime('%Y-%m-%d %H:%M:%S')
    strategy = data.get('strategy', 'N/A')
    codes = ', '.join(data.get('codes', []))
    date_range = f"{data.get('start_date', '')} ~ {data.get('end_date', '')}"
    elements.append(Paragraph(
        f'Strategy: {strategy} | Codes: {codes} | Period: {date_range} | Generated: {gen_time}',
        styles['SubTitleCN'],
    ))
    elements.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
    elements.append(Spacer(1, 4 * mm))

    # ── 核心指标 ──
    elements.append(Paragraph('Core Metrics', styles['SectionCN']))
    metrics = [
        ['Metric', 'Value', 'Metric', 'Value'],
        ['Total Return', _pct(data.get('total_return')), 'Annual Return', _pct(data.get('annual_return'))],
        ['Sharpe Ratio', _num(data.get('sharpe_ratio')), 'Sortino Ratio', _num(data.get('sortino_ratio'))],
        ['Max Drawdown', _pct(data.get('max_drawdown')), 'Calmar Ratio', _num(data.get('calmar_ratio'))],
        ['Win Rate', _pct(data.get('win_rate')), 'Profit/Loss Ratio', _num(data.get('profit_loss_ratio'))],
        ['Alpha', _num(data.get('alpha')), 'Beta', _num(data.get('beta'))],
        ['Info Ratio', _num(data.get('information_ratio')), 'Total Trades', str(data.get('total_trades', 0))],
        ['Max Consec. Wins', str(data.get('max_consecutive_wins', 0)), 'Max Consec. Losses', str(data.get('max_consecutive_losses', 0))],
    ]
    t = Table(metrics, colWidths=[42 * mm, 38 * mm, 42 * mm, 38 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a90d9')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f8f8')]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6 * mm))

    # ── 资金配置 ──
    elements.append(Paragraph('Capital Configuration', styles['SectionCN']))
    config_data = [
        ['Parameter', 'Value'],
        ['Initial Cash', f"¥{data.get('initial_cash', 0):,.2f}"],
        ['Commission Rate', _pct(data.get('commission_rate'))],
        ['Stamp Tax Rate', _pct(data.get('stamp_tax_rate'))],
        ['Slippage', _pct(data.get('slippage'))],
        ['Benchmark', data.get('benchmark', 'None')],
    ]
    ct = Table(config_data, colWidths=[50 * mm, 50 * mm])
    ct.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#5a6e5a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f8f8')]),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(ct)
    elements.append(Spacer(1, 6 * mm))

    # ── 交易明细 ──
    trades = data.get('trades', [])
    if trades:
        elements.append(Paragraph(f'Trade Details ({len(trades)} trades)', styles['SectionCN']))
        trade_rows = [['#', 'Date', 'Code', 'Action', 'Price', 'Volume', 'PnL']]
        for i, t in enumerate(trades[:50], 1):  # 最多显示50笔
            pnl = t.get('pnl', 0)
            pnl_str = f"¥{pnl:,.2f}" if pnl else '--'
            trade_rows.append([
                str(i),
                str(t.get('date', '')),
                str(t.get('code', '')),
                str(t.get('action', '')),
                f"¥{t.get('price', 0):.2f}",
                str(t.get('volume', 0)),
                pnl_str,
            ])
        tt = Table(trade_rows, colWidths=[10*mm, 25*mm, 20*mm, 15*mm, 22*mm, 18*mm, 22*mm])
        tt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6b5b95')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (4, 0), (-1, -1), 'RIGHT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f8f8')]),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(tt)
        if len(trades) > 50:
            elements.append(Paragraph(f'... and {len(trades) - 50} more trades', styles['BodyCN']))
        elements.append(Spacer(1, 6 * mm))

    # ── 风险告警 ──
    alerts = data.get('risk_alerts', [])
    if alerts:
        elements.append(Paragraph(f'Risk Alerts ({len(alerts)})', styles['SectionCN']))
        alert_rows = [['Date', 'Level', 'Category', 'Message']]
        for a in alerts[:20]:
            alert_rows.append([
                str(a.get('date', '')),
                str(a.get('level', '')),
                str(a.get('category', '')),
                str(a.get('message', ''))[:60],
            ])
        at = Table(alert_rows, colWidths=[25*mm, 15*mm, 20*mm, 100*mm])
        at.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c0392b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fff5f5')]),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(at)

    # ── 免责声明 ──
    elements.append(Spacer(1, 10 * mm))
    elements.append(HRFlowable(width='100%', thickness=0.5, color=colors.HexColor('#cccccc')))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        'Disclaimer: This report is for educational and research purposes only. '
        'Past performance does not guarantee future results. '
        'Please consult a licensed financial advisor before making investment decisions.',
        ParagraphStyle('Disclaimer', parent=styles['Normal'], fontSize=7,
                       textColor=colors.HexColor('#999999'), alignment=TA_CENTER),
    ))

    doc.build(elements)
    return buf.getvalue()


def _pct(val) -> str:
    if val is None:
        return '--'
    return f"{val * 100:.2f}%"


def _num(val) -> str:
    if val is None:
        return '--'
    return f"{val:.4f}"

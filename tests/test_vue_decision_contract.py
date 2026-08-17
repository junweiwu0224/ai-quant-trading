from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_ui(path: str) -> str:
    return (ROOT / "dashboard/ui/src" / path).read_text(encoding="utf-8")


def test_decision_view_keeps_research_scopes_market_boundaries_and_trust_metadata():
    source = read_ui("views/DecisionView.vue")

    for endpoint in (
        "api.marketRadar()",
        "api.decisionMatrix('signal')",
        "api.decisionMatrix('watchlist')",
        "api.watchlist()",
        "api.alertHistory()",
        "api.decisionMarkets()",
    ):
        assert endpoint in source

    assert "opportunityScope" in source
    assert "opportunityScope === 'signal'" in source
    assert "opportunityScope === 'watchlist'" in source
    assert "api.addWatchlist(normalized)" in source
    assert "api.removeWatchlist(code)" in source
    assert "currentMarketIsManualOnly" in source
    assert "provider_not_connected" in source or "市场能力清单尚未返回" in source
    assert "仅手动研究" in source
    for metadata in ("source", "generated_at", "stale", "coverage_pct"):
        assert metadata in source
    assert "研究优先级" in source
    assert "综合分" not in source


def test_report_index_keeps_share_url_on_the_report_row_and_uses_auth_detail_api():
    source = read_ui("views/ReportsView.vue")

    assert "api.post<DecisionShareResponse>(`/api/decisions/reports/${encodeURIComponent(report.id)}/share`, {})" in source
    assert "const publicUrl = new URL(data.url, window.location.origin).toString()" in source
    assert "report.share_url = publicUrl" in source
    assert ':href="report.share_url"' in source
    assert "@click=\"copyShareUrl(report)\"" in source
    assert "/api/decisions/reports/${encodeURIComponent(report.id)}" in source
    assert "/report/${report.id}" not in source
    assert "/api/decisions/delivery-attempts" in source
    assert "latestDeliveryStatus" in source


def test_notifications_and_settings_surface_delivery_failures_and_safe_workspace_controls():
    notifications = read_ui("views/NotificationsView.vue")
    settings = read_ui("views/SettingsView.vue")

    assert "/api/decisions/delivery-attempts" in notifications
    assert "failed" in notifications and "dead" in notifications
    assert "发送历史与失败队列" in notifications
    assert "/api/account/workspace/settings" in settings
    assert "daily_research_enabled" in settings
    assert "screening_enabled" in settings
    assert "worker_process_ready" in settings
    assert "worker_automation_enabled" in settings
    assert "决策 Worker 进程" in settings
    assert "工作区自动任务" in settings
    assert "vue_app_default" not in settings
    assert "统一决策工作台" in settings
    assert "decision_auto_push_enabled" not in settings


def test_shared_report_reads_token_endpoint_and_surfaces_public_read_only_metadata():
    source = read_ui("views/SharedReportView.vue")

    assert "api.get<SharedDecisionReport>(`/api/decisions/shared/${encodeURIComponent(token)}`)" in source
    assert "/api/decisions/reports/" not in source
    assert "只读报告" in source
    assert "有效期至 {{ report.expires_at || '不可用' }}" in source
    assert "报告 hash {{ shortHash(report.report_hash) }}" in source
    assert "市场能力与策略版本" in source
    assert "验证摘要与关键证据" in source
    assert "AI 解释与投递历史" in source
    assert "workspace" not in source.lower()


def test_report_route_survives_query_and_hash_without_legacy_redirect():
    source = read_ui("router.ts")

    assert "{ path: '/report/:token'" in source
    assert "if (to.path.startsWith('/report/'))" in source
    assert "const hash = to.hash.replace(/^#/, '')" in source
    assert "window.location.hash" not in source
    assert "window.location.search" not in source

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_more_view_is_a_small_system_directory() -> None:
    source = (ROOT / "dashboard/ui/src/views/MoreView.vue").read_text(encoding="utf-8")
    assert "工作区工具目录" in source
    assert "不会在此页隐藏研究或交易主流程" in source
    for route in ("/app/reports", "/app/notifications", "/app/settings", "/app/broker"):
        assert route in source
    assert "/app/more/" not in source


def test_more_view_links_only_to_canonical_system_workflows() -> None:
    source = (ROOT / "dashboard/ui/src/views/MoreView.vue").read_text(encoding="utf-8")

    assert ':to="item.route"' in source
    assert "api.get(" not in source
    assert "/app/more/" not in source

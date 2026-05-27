from html.parser import HTMLParser
from pathlib import Path


class _TagCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_openclaw_is_contextual_tool_not_primary_navigation():
    template = Path("dashboard/templates/index.html").read_text(encoding="utf-8")
    parser = _TagCollector()
    parser.feed(template)
    anchors = [attrs for tag, attrs in parser.tags if tag == "a"]
    panels = [attrs for tag, attrs in parser.tags if tag == "section"]

    assert all(attrs.get("id") != "nav-openclaw" for attrs in anchors)
    assert all(attrs.get("id") != "m-nav-openclaw" for attrs in anchors)
    assert not any(
        attrs.get("data-tab") == "openclaw" and attrs.get("role") == "tab"
        for attrs in anchors
    )

    assert any(
        attrs.get("id") == "tab-openclaw" and attrs.get("aria-label") == "龙虾工作区"
        for attrs in panels
    )
    assert 'id="copilot-fab"' in template
    assert "问龙虾" in template or "ask" in template

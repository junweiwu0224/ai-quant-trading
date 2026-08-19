"""
Integration tests for ResearchView component.

Tests verify:
- Routing configuration (market/symbol params)
- Tab structure and labels
- Component rendering in all 3 tabs
- Responsive layouts
- Design token usage
- Theme support
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
UI_ROOT = PROJECT_ROOT / "dashboard" / "ui" / "src"


def read_vue_file(path: Path) -> str:
    """Read a Vue component file."""
    assert path.exists(), f"File not found: {path}"
    return path.read_text(encoding="utf-8")


def has_section(content: str, section: str) -> bool:
    """Check if component has a specific section (script, template, style)."""
    pattern = rf"<{section}[^>]*>.*?</{section}>"
    return bool(re.search(pattern, content, re.DOTALL))


def extract_section(content: str, section: str) -> str:
    """Extract a specific section from Vue component."""
    pattern = rf"<{section}[^>]*>(.*?)</{section}>"
    match = re.search(pattern, content, re.DOTALL)
    return match.group(1) if match else ""


# ============================================================================
# Routing Tests
# ============================================================================

def test_research_view_route_exists():
    """Verify ResearchView route is defined in router."""
    router_path = UI_ROOT / "router.ts"
    content = read_vue_file(router_path)

    # Check route definition with market and symbol params
    assert "/app/research/:market/:symbol" in content, \
        "Router should define /app/research/:market/:symbol route"

    # Check component import
    assert "ResearchView.vue" in content, \
        "Router should import ResearchView component"


def test_research_view_default_redirect():
    """Verify default redirect from /app/research works."""
    router_path = UI_ROOT / "router.ts"
    content = read_vue_file(router_path)

    # Check default redirect
    assert re.search(r"/app/research.*redirect.*600519", content), \
        "Router should redirect /app/research to default symbol"


def test_research_view_accepts_params():
    """Verify ResearchView extracts route params correctly."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")

    # Check useRoute import
    assert "useRoute" in script, "Should import useRoute"

    # Check param extraction
    assert re.search(r"route\.params\.symbol", script), \
        "Should extract symbol from route params"
    assert re.search(r"route\.params\.market", script), \
        "Should extract market from route params"


def test_route_params_computed():
    """Verify route params are reactive computed values."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")

    # Check computed is imported
    assert "computed" in script, "Should import computed from vue"

    # Check symbol and market are computed
    assert re.search(r"symbol\s*=\s*computed", script), \
        "symbol should be a computed property"
    assert re.search(r"market\s*=\s*computed", script), \
        "market should be a computed property"


# ============================================================================
# Tab Structure Tests
# ============================================================================

def test_research_view_has_three_tabs():
    """Verify ResearchView has exactly 3 tabs."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")

    # Check tabs array definition
    assert "tabs:" in script or "const tabs" in script, \
        "Should define tabs array"

    # Count tab definitions (id + label pairs)
    tab_matches = re.findall(r"{[^}]*id:[^}]*label:[^}]*}", script)
    assert len(tab_matches) == 3, \
        f"Should have exactly 3 tabs, found {len(tab_matches)}"


def test_tab_labels_correct():
    """Verify tab labels are correct."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")

    # Check tab labels
    assert "K线与技术" in content, "Should have 'K线与技术' tab"
    assert "证据与决策" in content, "Should have '证据与决策' tab"
    assert "回测草案" in content, "Should have '回测草案' tab"


def test_tab_ids_defined():
    """Verify tab IDs are properly defined."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")

    # Check for tab IDs
    assert re.search(r"id:\s*['\"]kline-tech['\"]", script), \
        "Should have kline-tech tab id"
    assert re.search(r"id:\s*['\"]evidence['\"]", script), \
        "Should have evidence tab id"
    assert re.search(r"id:\s*['\"]backtest['\"]", script), \
        "Should have backtest tab id"


def test_active_tab_state():
    """Verify activeTab state management."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")

    # Check activeTab ref
    assert "activeTab" in script, "Should have activeTab state"
    assert re.search(r"activeTab\s*=\s*ref", script), \
        "activeTab should be a ref"

    # Default should be first tab
    assert re.search(r"ref\(['\"]kline-tech['\"]", script), \
        "Default activeTab should be 'kline-tech'"


def test_base_tabs_integration():
    """Verify BaseTabs component is used correctly."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")
    template = extract_section(content, "template")

    # Check import
    assert "BaseTabs" in script, "Should import BaseTabs"
    assert "from '../components/base/BaseTabs.vue'" in script, \
        "Should import BaseTabs from correct path"

    # Check usage in template
    assert "<BaseTabs" in template, "Should use <BaseTabs> in template"
    assert 'v-model="activeTab"' in template, \
        "Should bind activeTab with v-model"
    assert ':tabs="tabs"' in template, \
        "Should pass tabs array as prop"


# ============================================================================
# Component Rendering Tests
# ============================================================================

def test_tab1_renders_chart_and_indicators():
    """Verify Tab 1 renders KLineChart and TechnicalIndicators."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")
    template = extract_section(content, "template")

    # Check imports
    assert "KLineChart" in script, "Should import KLineChart"
    assert "TechnicalIndicators" in script, "Should import TechnicalIndicators"

    # Check template usage in kline-tech tab
    kline_section = re.search(
        r"activeTab\s*===\s*['\"]kline-tech['\"].*?</div>",
        template,
        re.DOTALL
    )
    assert kline_section, "Should have kline-tech tab section"

    kline_content = kline_section.group(0)
    assert "<KLineChart" in kline_content, \
        "kline-tech tab should render KLineChart"
    assert "<TechnicalIndicators" in kline_content, \
        "kline-tech tab should render TechnicalIndicators"


def test_tab2_renders_evidence_and_decision():
    """Verify Tab 2 renders EvidenceChain and DecisionCard."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")
    template = extract_section(content, "template")

    # Check imports
    assert "EvidenceChain" in script, "Should import EvidenceChain"
    assert "DecisionCard" in script, "Should import DecisionCard"

    # Check template usage in evidence tab
    evidence_section = re.search(
        r"activeTab\s*===\s*['\"]evidence['\"].*?</div>",
        template,
        re.DOTALL
    )
    assert evidence_section, "Should have evidence tab section"

    evidence_content = evidence_section.group(0)
    assert "<EvidenceChain" in evidence_content, \
        "evidence tab should render EvidenceChain"
    assert "<DecisionCard" in evidence_content, \
        "evidence tab should render DecisionCard"


def test_tab3_renders_validation_handoff():
    """Verify the backtest tab hands off to the real validation workflow."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")
    template = extract_section(content, "template")

    assert "BacktestDraft" in script, "Should import BacktestDraft"
    assert "BacktestPreview" not in script, "Should not import the removed placeholder preview"

    backtest_section = re.search(
        r"activeTab\s*===\s*['\"]backtest['\"].*?</div>",
        template,
        re.DOTALL
    )
    assert backtest_section, "Should have backtest tab section"

    backtest_content = backtest_section.group(0)
    assert "<BacktestDraft" in backtest_content, "backtest tab should render the validation handoff"
    assert "<BacktestPreview" not in backtest_content

    handoff = read_vue_file(UI_ROOT / "components" / "research" / "BacktestDraft.vue")
    assert "打开验证工作区" in handoff
    assert "不会保存本地草案或生成占位结果" in handoff


def test_components_receive_market_symbol_props():
    """Verify all child components receive market and symbol props."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    template = extract_section(content, "template")

    components = [
        "KLineChart",
        "TechnicalIndicators",
        "EvidenceChain",
        "DecisionCard",
        "BacktestDraft"
    ]

    for component in components:
        component_match = re.search(
            rf"<{component}[^>]*>",
            template
        )
        assert component_match, f"{component} should be in template"

        component_tag = component_match.group(0)
        assert ':market="market"' in component_tag, \
            f"{component} should receive :market prop"
        assert ':symbol="symbol"' in component_tag, \
            f"{component} should receive :symbol prop"


# ============================================================================
# Responsive Tests
# ============================================================================

def test_responsive_breakpoint_768px():
    """Verify 768px breakpoint exists for mobile layout."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check for 768px breakpoint
    assert re.search(r"@media.*max-width.*768px", style), \
        "Should have @media query for 768px breakpoint"


def test_responsive_breakpoint_480px():
    """Verify 480px breakpoint exists for small mobile."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check for 480px breakpoint
    assert re.search(r"@media.*max-width.*480px", style), \
        "Should have @media query for 480px breakpoint"


def test_backtest_handoff_is_responsive():
    """Verify the real validation handoff remains usable on narrow screens."""
    component = read_vue_file(UI_ROOT / "components" / "research" / "BacktestDraft.vue")
    style = extract_section(component, "style")

    assert ".backtest-handoff" in style
    assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in style
    assert re.search(r"@media.*max-width.*600px", style)
    assert "grid-template-columns: 1fr" in style


def test_research_header_responsive():
    """Verify research header adapts to mobile."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check header exists
    assert ".research-header" in style, "Should have .research-header styles"

    # Check mobile adaptation
    mobile_section = re.search(
        r"@media.*max-width.*768px.*?{(.*?)}(?=\s*(?:@media|/\*|$))",
        style,
        re.DOTALL
    )
    if mobile_section:
        mobile_styles = mobile_section.group(0)
        if "research-header" in mobile_styles:
            assert "flex-direction: column" in mobile_styles or \
                   "flex-direction:column" in mobile_styles, \
                "research-header should stack on mobile"


# ============================================================================
# Design Token Tests
# ============================================================================

def test_components_use_css_variables():
    """Verify ResearchView uses CSS variables, not hardcoded values."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check for CSS variable usage
    assert "var(--spacing-" in style, \
        "Should use spacing CSS variables"
    assert "var(--color-" in style, \
        "Should use color CSS variables"
    assert "var(--font-size-" in style, \
        "Should use font-size CSS variables"


def test_no_hardcoded_colors():
    """Verify no hardcoded color values (hex, rgb)."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Remove comments to avoid false positives
    style_no_comments = re.sub(r"/\*.*?\*/", "", style, flags=re.DOTALL)

    # Check for hardcoded colors (allow rgba with 0 opacity for transparency)
    hex_colors = re.findall(r":\s*#[0-9a-fA-F]{3,6}", style_no_comments)
    # Filter out common exceptions like #fff in comments or data-uris
    hex_colors = [c for c in hex_colors if "url(" not in style_no_comments[max(0, style_no_comments.find(c)-10):style_no_comments.find(c)]]

    assert len(hex_colors) == 0, \
        f"Should not use hardcoded hex colors, found: {hex_colors}"


def test_spacing_tokens_usage():
    """Verify spacing tokens are used correctly."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check various spacing tokens
    spacing_tokens = [
        "var(--spacing-xs)",
        "var(--spacing-sm)",
        "var(--spacing-md)",
        "var(--spacing-lg)",
        "var(--spacing-xl)"
    ]

    found_tokens = [token for token in spacing_tokens if token in style]
    assert len(found_tokens) >= 3, \
        f"Should use at least 3 different spacing tokens, found: {found_tokens}"


def test_color_tokens_usage():
    """Verify color tokens are used correctly."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check various color tokens
    color_tokens = [
        "var(--color-ink",
        "var(--color-line",
        "var(--color-accent",
        "var(--color-surface"
    ]

    found_tokens = [token for token in color_tokens if token in style]
    assert len(found_tokens) >= 2, \
        f"Should use multiple color tokens, found: {found_tokens}"


def test_radius_tokens_usage():
    """Verify border-radius tokens are used."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check for radius tokens
    assert "var(--radius-" in style, \
        "Should use border-radius CSS variables"


def test_animation_tokens_usage():
    """Verify animation/transition tokens are used."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check for animation tokens
    has_duration = "var(--duration-" in style
    has_ease = "var(--ease-" in style

    assert has_duration or has_ease, \
        "Should use animation tokens (duration or ease)"


# ============================================================================
# Theme Support Tests
# ============================================================================

def test_scoped_styles():
    """Verify styles are scoped to component."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    # Check for scoped attribute
    assert re.search(r"<style[^>]*scoped", content), \
        "Styles should be scoped"


def test_semantic_class_names():
    """Verify semantic, BEM-style class names are used."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check for research- prefixed classes
    classes = [
        ".research-view",
        ".research-header",
        ".research-title",
        ".research-meta"
    ]

    for cls in classes:
        assert cls in style, f"Should define {cls} class"


def test_layout_container_classes():
    """Verify layout container classes are defined."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check layout classes
    layout_classes = [
        ".research-layout",
        ".evidence-layout"
    ]

    for cls in layout_classes:
        assert cls in style, f"Should define {cls} class"


# ============================================================================
# Child Component Tests
# ============================================================================

def test_all_child_components_exist():
    """Verify all research child components exist."""
    components_dir = UI_ROOT / "components" / "research"

    components = [
        "KLineChart.vue",
        "TechnicalIndicators.vue",
        "EvidenceChain.vue",
        "DecisionCard.vue",
        "BacktestDraft.vue"
    ]

    for component in components:
        path = components_dir / component
        assert path.exists(), f"Component {component} should exist"


def test_child_components_have_props():
    """Verify child components accept market and symbol props."""
    components_dir = UI_ROOT / "components" / "research"

    components = [
        "KLineChart.vue",
        "TechnicalIndicators.vue",
        "EvidenceChain.vue",
        "DecisionCard.vue",
        "BacktestDraft.vue"
    ]

    for component_name in components:
        path = components_dir / component_name
        content = read_vue_file(path)

        script = extract_section(content, "script")

        # Check for props definition
        assert "defineProps" in script or "props:" in script, \
            f"{component_name} should define props"

        # Check for market and symbol props
        assert "market" in script, \
            f"{component_name} should have market prop"
        assert "symbol" in script, \
            f"{component_name} should have symbol prop"


def test_child_components_use_design_tokens():
    """Verify child components use design tokens."""
    components_dir = UI_ROOT / "components" / "research"

    components = [
        "KLineChart.vue",
        "TechnicalIndicators.vue",
        "EvidenceChain.vue",
        "DecisionCard.vue",
        "BacktestDraft.vue"
    ]

    for component_name in components:
        path = components_dir / component_name
        content = read_vue_file(path)

        if has_section(content, "style"):
            style = extract_section(content, "style")

            # Should use CSS variables
            has_vars = any(var in style for var in [
                "var(--spacing-",
                "var(--color-",
                "var(--font-size-",
                "var(--radius-"
            ])

            assert has_vars, \
                f"{component_name} should use CSS design tokens"


# ============================================================================
# Structure Tests
# ============================================================================

def test_research_view_structure():
    """Verify ResearchView has proper Vue component structure."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    assert has_section(content, "script"), \
        "ResearchView should have <script> section"
    assert has_section(content, "template"), \
        "ResearchView should have <template> section"
    assert has_section(content, "style"), \
        "ResearchView should have <style> section"


def test_script_setup_syntax():
    """Verify ResearchView uses script setup syntax."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    # Check for setup attribute
    assert re.search(r"<script[^>]*setup", content), \
        "Should use <script setup> syntax"


def test_typescript_enabled():
    """Verify ResearchView uses TypeScript."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    # Check for lang="ts" attribute
    assert re.search(r"<script[^>]*lang=['\"]ts['\"]", content), \
        "Should use TypeScript (lang='ts')"


# ============================================================================
# Integration Tests
# ============================================================================

def test_all_imports_valid():
    """Verify all component imports resolve correctly."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")

    # Extract all imports
    imports = re.findall(r"from ['\"](.+?)['\"]", script)

    for import_path in imports:
        if import_path.startswith('.'):
            # Resolve relative path
            resolved = (view_path.parent / import_path).resolve()
            if not resolved.suffix:
                # Vue imports commonly omit the extension for TS/JS modules.
                candidates = [
                    resolved.with_suffix(extension)
                    for extension in ('.vue', '.ts', '.tsx', '.js', '.jsx')
                ]
                resolved = next((candidate for candidate in candidates if candidate.exists()), candidates[0])

            # Check file exists
            assert resolved.exists(), \
                f"Import {import_path} should resolve to existing file: {resolved}"


def test_tab_type_import():
    """Verify Tab type is imported from BaseTabs."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    script = extract_section(content, "script")

    # Check for Tab type import
    assert re.search(r"import.*type.*Tab.*from.*BaseTabs", script), \
        "Should import Tab type from BaseTabs"


def test_max_width_container():
    """Verify ResearchView has max-width container."""
    view_path = UI_ROOT / "views" / "ResearchView.vue"
    content = read_vue_file(view_path)

    style = extract_section(content, "style")

    # Check for max-width on main container
    assert re.search(r"\.research-view\s*{[^}]*max-width", style, re.DOTALL), \
        "research-view should have max-width constraint"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

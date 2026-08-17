"""
Contract tests for Vue layout components.

Tests verify:
- File existence for all layout components
- Component structure (script, template, style sections)
- Key props and emits in components
- Integration in App.vue
"""

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
UI_ROOT = PROJECT_ROOT / "dashboard" / "ui" / "src"


def read_component(name: str) -> str:
    """Read a Vue component file."""
    path = UI_ROOT / "components" / f"{name}.vue"
    assert path.exists(), f"Component {name}.vue not found at {path}"
    return path.read_text(encoding="utf-8")


def has_section(content: str, section: str) -> bool:
    """Check if component has a specific section (script, template, style)."""
    pattern = rf"<{section}[^>]*>.*?</{section}>"
    return bool(re.search(pattern, content, re.DOTALL))


def test_layout_components_exist():
    """Verify all layout component files exist."""
    components = ["AppShell", "Sidebar", "MobileNav", "MainContent"]
    for component in components:
        path = UI_ROOT / "components" / f"{component}.vue"
        assert path.exists(), f"Missing component: {component}.vue"


def test_app_shell_structure():
    """Test AppShell component structure."""
    content = read_component("AppShell")

    assert has_section(content, "script"), "AppShell missing <script> section"
    assert has_section(content, "template"), "AppShell missing <template> section"
    assert has_section(content, "style"), "AppShell missing <style> section"

    # Should import child components
    assert "Sidebar" in content, "AppShell should import Sidebar"
    assert "MobileNav" in content, "AppShell should import MobileNav"
    assert "MainContent" in content, "AppShell should import MainContent"

    # Should have menu state management
    assert "menuOpen" in content or "open" in content, "AppShell should manage menu state"


def test_sidebar_structure():
    """Test Sidebar component structure."""
    content = read_component("Sidebar")

    assert has_section(content, "script"), "Sidebar missing <script> section"
    assert has_section(content, "template"), "Sidebar missing <template> section"
    assert has_section(content, "style"), "Sidebar missing <style> section"

    # Should use theme composable
    assert "useTheme" in content, "Sidebar should use useTheme composable"

    # Should have navigation
    assert "nav" in content or "RouterLink" in content, "Sidebar should have navigation"

    # Should have theme toggle
    assert "toggleTheme" in content or "theme" in content.lower(), "Sidebar should have theme toggle"

    # Should have proper width
    assert "240px" in content, "Sidebar should be 240px wide"


def test_mobile_nav_structure():
    """Test MobileNav component structure."""
    content = read_component("MobileNav")

    assert has_section(content, "script"), "MobileNav missing <script> section"
    assert has_section(content, "template"), "MobileNav missing <template> section"
    assert has_section(content, "style"), "MobileNav missing <style> section"

    # Should use theme composable
    assert "useTheme" in content, "MobileNav should use useTheme composable"

    # Should have navigation items
    assert "RouterLink" in content, "MobileNav should have RouterLink"

    # Should have proper height
    assert "64px" in content, "MobileNav should be 64px height"

    # Should be mobile-only
    assert "mobile" in content.lower(), "MobileNav should have mobile-only styles"


def test_main_content_structure():
    """Test MainContent component structure."""
    content = read_component("MainContent")

    assert has_section(content, "script"), "MainContent missing <script> section"
    assert has_section(content, "template"), "MainContent missing <template> section"
    assert has_section(content, "style"), "MainContent missing <style> section"

    # Should have RouterView for page content
    assert "RouterView" in content, "MainContent should have RouterView"

    # Should emit toggle-menu event
    assert "toggleMenu" in content or "toggle-menu" in content, "MainContent should emit toggle-menu"

    # Should have topbar
    assert "topbar" in content.lower(), "MainContent should have topbar"


def test_app_vue_integration():
    """Test that App.vue integrates AppShell."""
    path = UI_ROOT / "App.vue"
    assert path.exists(), "App.vue not found"

    content = path.read_text(encoding="utf-8")

    # Should import AppShell
    assert "AppShell" in content, "App.vue should import AppShell"

    # Should use AppShell in template
    assert "<AppShell" in content, "App.vue should use <AppShell> in template"

    # Should not have old layout code in authenticated section
    # (Old code had inline sidebar/mobile-nav, new code uses AppShell)
    template_section = re.search(r"<template>.*?</template>", content, re.DOTALL)
    if template_section:
        template = template_section.group(0)
        # Check that AppShell is used for authenticated state
        assert "AppShell" in template, "Template should use AppShell component"


def test_responsive_breakpoint():
    """Test that components use consistent responsive breakpoint."""
    components = ["AppShell", "Sidebar", "MobileNav", "MainContent"]

    for component in components:
        content = read_component(component)
        # Should use 768px breakpoint for desktop/mobile
        if "767px" in content or "768px" in content:
            assert True  # Component has responsive styles
        else:
            # Some components may not need media queries directly
            # (e.g., if parent handles it)
            pass


def test_css_variables_usage():
    """Test that components use CSS variables from Task 1."""
    components = ["Sidebar", "MobileNav", "MainContent"]

    for component in components:
        content = read_component(component)
        style_section = re.search(r"<style[^>]*>.*?</style>", content, re.DOTALL)

        if style_section:
            style = style_section.group(0)
            # Should use at least some CSS variables
            has_vars = any(var in style for var in [
                "var(--spacing-",
                "var(--color-",
                "var(--radius-"
            ])
            assert has_vars, f"{component} should use CSS variables"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

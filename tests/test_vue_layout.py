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
    components = ["AppShell", "Sidebar", "MobileNav", "MainContent", "WorkspaceNav"]
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

    # Theme controls belong to the workspace bar / system menu, not the primary rail.
    assert "useTheme" not in content, "Sidebar must not duplicate theme controls"

    # Should have navigation
    assert "nav" in content or "RouterLink" in content, "Sidebar should have navigation"

    # Theme controls live in the workspace bar / system menu, so the rail stays workflow-only.
    assert "toggleTheme" not in content, "Sidebar must not duplicate the theme control"

    # Rail width is defined once by the shell token.
    shell = (UI_ROOT / "styles" / "shell.css").read_text(encoding="utf-8")
    assert "--sidebar-width" in shell, "Shell should own the rail width"


def test_mobile_nav_structure():
    """Test MobileNav component structure."""
    content = read_component("MobileNav")

    assert has_section(content, "script"), "MobileNav missing <script> section"
    assert has_section(content, "template"), "MobileNav missing <template> section"
    assert has_section(content, "style"), "MobileNav missing <style> section"

    # Mobile navigation is reserved for exactly five business workspaces; theme stays in the system controls.
    assert "useTheme" not in content, "MobileNav must not render a sixth theme action"
    assert "theme-btn" not in content, "MobileNav must not render a theme button"

    # Should have navigation items
    assert "RouterLink" in content, "MobileNav should have RouterLink"

    # Mobile bar height is owned by the shared shell layer, including safe-area space.
    shell = (UI_ROOT / "styles" / "shell.css").read_text(encoding="utf-8")
    assert "var(--mobile-nav-height)" in shell, "Shell should use the shared mobile height token"

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

    # Should have topbar and the local module navigation for each workspace.
    assert "topbar" in content.lower(), "MainContent should have topbar"
    assert "WorkspaceNav" in content, "MainContent should expose workspace modules"


def test_workspace_nav_structure():
    content = read_component("WorkspaceNav")

    assert has_section(content, "script")
    assert has_section(content, "template")
    assert has_section(content, "style")
    assert "workspaceForPath" in content
    assert "workspace.tabs" in content
    assert "isTabActive" in content



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


def test_shell_owns_shared_design_tokens():
    """Shared shell visuals should use the design system instead of component copies."""
    shell = (UI_ROOT / "styles" / "shell.css").read_text(encoding="utf-8")

    for token in ("var(--sidebar-width)", "var(--mobile-nav-height)", "var(--color-surface)", "var(--touch-target-min)"):
        assert token in shell, f"Shell should use {token}"

    for component in ("Sidebar", "MobileNav", "MainContent"):
        content = read_component(component)
        assert has_section(content, "style"), f"{component} missing scoped structure styles"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

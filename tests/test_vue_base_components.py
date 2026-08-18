"""
Test suite for Vue base components
Tests component rendering, theme support, and accessibility

These are optional browser tests. The default Python test suite only collects
and runs tests that do not require a browser installation; set
``RUN_PLAYWRIGHT_TESTS=1`` to opt into this suite after installing Playwright
and its browsers.
"""

import os

import pytest

pytestmark = pytest.mark.e2e
if os.environ.get("RUN_PLAYWRIGHT_TESTS", "").lower() not in {"1", "true", "yes", "on"}:
    pytest.skip("Playwright E2E tests are opt-in; set RUN_PLAYWRIGHT_TESTS=1", allow_module_level=True)

playwright = pytest.importorskip("playwright.sync_api", reason="install the optional Playwright Python package")
Page = playwright.Page
expect = playwright.expect
import time


@pytest.fixture
def test_page_url(live_server):
    """Create a test page that loads all base components"""
    return f"{live_server.url}/test-base-components.html"


def test_base_button_variants(page: Page, test_page_url: str):
    """Test BaseButton renders all variants correctly"""
    page.goto(test_page_url)

    # Wait for Vue app to mount
    page.wait_for_selector('[data-test="button-primary"]', timeout=5000)

    # Test primary button
    primary_btn = page.locator('[data-test="button-primary"]')
    expect(primary_btn).to_be_visible()
    expect(primary_btn).to_have_class(lambda classes: 'base-button--primary' in classes)

    # Test secondary button
    secondary_btn = page.locator('[data-test="button-secondary"]')
    expect(secondary_btn).to_have_class(lambda classes: 'base-button--secondary' in classes)

    # Test ghost button
    ghost_btn = page.locator('[data-test="button-ghost"]')
    expect(ghost_btn).to_have_class(lambda classes: 'base-button--ghost' in classes)

    # Test danger button
    danger_btn = page.locator('[data-test="button-danger"]')
    expect(danger_btn).to_have_class(lambda classes: 'base-button--danger' in classes)


def test_base_button_sizes(page: Page, test_page_url: str):
    """Test BaseButton renders all sizes correctly"""
    page.goto(test_page_url)

    small_btn = page.locator('[data-test="button-small"]')
    expect(small_btn).to_have_class(lambda classes: 'base-button--sm' in classes)

    medium_btn = page.locator('[data-test="button-medium"]')
    expect(medium_btn).to_have_class(lambda classes: 'base-button--md' in classes)

    large_btn = page.locator('[data-test="button-large"]')
    expect(large_btn).to_have_class(lambda classes: 'base-button--lg' in classes)

    # Verify medium button meets touch target minimum (44px)
    box = medium_btn.bounding_box()
    assert box is not None
    assert box['height'] >= 44, "Button height should meet 44px touch target minimum"


def test_base_button_interactions(page: Page, test_page_url: str):
    """Test BaseButton click interactions and disabled state"""
    page.goto(test_page_url)

    # Test normal button click
    click_btn = page.locator('[data-test="button-clickable"]')
    click_btn.click()
    expect(page.locator('[data-test="click-counter"]')).to_have_text('1')

    # Test disabled button doesn't trigger clicks
    disabled_btn = page.locator('[data-test="button-disabled"]')
    expect(disabled_btn).to_be_disabled()
    expect(disabled_btn).to_have_class(lambda classes: 'base-button--disabled' in classes)


def test_base_button_loading_state(page: Page, test_page_url: str):
    """Test BaseButton loading state"""
    page.goto(test_page_url)

    loading_btn = page.locator('[data-test="button-loading"]')
    expect(loading_btn).to_have_class(lambda classes: 'base-button--loading' in classes)

    # Should show spinner
    spinner = loading_btn.locator('.base-button__spinner')
    expect(spinner).to_be_visible()


def test_base_card_variants(page: Page, test_page_url: str):
    """Test BaseCard renders with different props"""
    page.goto(test_page_url)

    # Test default card
    default_card = page.locator('[data-test="card-default"]')
    expect(default_card).to_be_visible()
    expect(default_card).to_have_class(lambda classes: 'base-card' in classes)

    # Test elevated card has shadow
    elevated_card = page.locator('[data-test="card-elevated"]')
    expect(elevated_card).to_have_class(lambda classes: 'base-card--elevated' in classes)

    # Test hoverable card
    hoverable_card = page.locator('[data-test="card-hoverable"]')
    expect(hoverable_card).to_have_class(lambda classes: 'base-card--hoverable' in classes)


def test_base_card_padding(page: Page, test_page_url: str):
    """Test BaseCard padding variants"""
    page.goto(test_page_url)

    small_card = page.locator('[data-test="card-padding-sm"]')
    expect(small_card).to_have_class(lambda classes: 'base-card--padding-sm' in classes)

    medium_card = page.locator('[data-test="card-padding-md"]')
    expect(medium_card).to_have_class(lambda classes: 'base-card--padding-md' in classes)

    large_card = page.locator('[data-test="card-padding-lg"]')
    expect(large_card).to_have_class(lambda classes: 'base-card--padding-lg' in classes)


def test_base_input_basic(page: Page, test_page_url: str):
    """Test BaseInput basic functionality"""
    page.goto(test_page_url)

    input_field = page.locator('[data-test="input-basic"]')
    expect(input_field).to_be_visible()
    expect(input_field).to_have_class(lambda classes: 'base-input' in classes)

    # Test input interaction
    input_field.fill('Test input')
    expect(input_field).to_have_value('Test input')


def test_base_input_sizes(page: Page, test_page_url: str):
    """Test BaseInput size variants"""
    page.goto(test_page_url)

    small_input = page.locator('[data-test="input-small"]')
    expect(small_input).to_have_class(lambda classes: 'base-input--sm' in classes)

    medium_input = page.locator('[data-test="input-medium"]')
    expect(medium_input).to_have_class(lambda classes: 'base-input--md' in classes)
    box = medium_input.bounding_box()
    assert box is not None
    assert box['height'] >= 44, "Input height should meet 44px touch target minimum"

    large_input = page.locator('[data-test="input-large"]')
    expect(large_input).to_have_class(lambda classes: 'base-input--lg' in classes)


def test_base_input_error_state(page: Page, test_page_url: str):
    """Test BaseInput error state"""
    page.goto(test_page_url)

    error_input = page.locator('[data-test="input-error"]')
    expect(error_input).to_have_class(lambda classes: 'base-input--error' in classes)

    # Check error message is displayed
    error_msg = page.locator('[data-test="input-error-message"]')
    expect(error_msg).to_be_visible()
    expect(error_msg).to_have_class(lambda classes: 'base-input__error' in classes)


def test_base_input_disabled(page: Page, test_page_url: str):
    """Test BaseInput disabled state"""
    page.goto(test_page_url)

    disabled_input = page.locator('[data-test="input-disabled"]')
    expect(disabled_input).to_be_disabled()
    expect(disabled_input).to_have_class(lambda classes: 'base-input--disabled' in classes)


def test_base_select_basic(page: Page, test_page_url: str):
    """Test BaseSelect basic functionality"""
    page.goto(test_page_url)

    select = page.locator('[data-test="select-basic"]')
    expect(select).to_be_visible()

    # Click to open dropdown
    select.click()
    expect(select).to_have_class(lambda classes: 'base-select--open' in classes)

    # Check dropdown is visible
    dropdown = page.locator('.base-select__dropdown')
    expect(dropdown).to_be_visible()

    # Select an option
    option = page.locator('.base-select__option').first
    option.click()

    # Dropdown should close after selection
    time.sleep(0.2)  # Wait for transition
    expect(dropdown).not_to_be_visible()


def test_base_select_disabled_option(page: Page, test_page_url: str):
    """Test BaseSelect disabled options"""
    page.goto(test_page_url)

    select = page.locator('[data-test="select-with-disabled"]')
    select.click()

    disabled_option = page.locator('[data-test="option-disabled"]')
    expect(disabled_option).to_have_class(lambda classes: 'base-select__option--disabled' in classes)


def test_base_tabs_basic(page: Page, test_page_url: str):
    """Test BaseTabs basic functionality"""
    page.goto(test_page_url)

    tabs_nav = page.locator('[data-test="tabs-nav"]')
    expect(tabs_nav).to_be_visible()

    # First tab should be active by default
    first_tab = page.locator('[data-test="tab-first"]')
    expect(first_tab).to_have_class(lambda classes: 'base-tabs__tab--active' in classes)

    # Click second tab
    second_tab = page.locator('[data-test="tab-second"]')
    second_tab.click()
    expect(second_tab).to_have_class(lambda classes: 'base-tabs__tab--active' in classes)
    expect(first_tab).not_to_have_class(lambda classes: 'base-tabs__tab--active' in classes)


def test_base_tabs_with_badge(page: Page, test_page_url: str):
    """Test BaseTabs with badge"""
    page.goto(test_page_url)

    tab_with_badge = page.locator('[data-test="tab-with-badge"]')
    badge = tab_with_badge.locator('.base-tabs__badge')
    expect(badge).to_be_visible()
    expect(badge).to_have_text('3')


def test_base_tabs_disabled(page: Page, test_page_url: str):
    """Test BaseTabs disabled state"""
    page.goto(test_page_url)

    disabled_tab = page.locator('[data-test="tab-disabled"]')
    expect(disabled_tab).to_be_disabled()
    expect(disabled_tab).to_have_class(lambda classes: 'base-tabs__tab--disabled' in classes)


def test_base_tag_variants(page: Page, test_page_url: str):
    """Test BaseTag variants"""
    page.goto(test_page_url)

    default_tag = page.locator('[data-test="tag-default"]')
    expect(default_tag).to_have_class(lambda classes: 'base-tag--default' in classes)

    success_tag = page.locator('[data-test="tag-success"]')
    expect(success_tag).to_have_class(lambda classes: 'base-tag--success' in classes)

    warning_tag = page.locator('[data-test="tag-warning"]')
    expect(warning_tag).to_have_class(lambda classes: 'base-tag--warning' in classes)

    danger_tag = page.locator('[data-test="tag-danger"]')
    expect(danger_tag).to_have_class(lambda classes: 'base-tag--danger' in classes)

    up_tag = page.locator('[data-test="tag-up"]')
    expect(up_tag).to_have_class(lambda classes: 'base-tag--up' in classes)

    down_tag = page.locator('[data-test="tag-down"]')
    expect(down_tag).to_have_class(lambda classes: 'base-tag--down' in classes)


def test_base_tag_closable(page: Page, test_page_url: str):
    """Test BaseTag closable functionality"""
    page.goto(test_page_url)

    closable_tag = page.locator('[data-test="tag-closable"]')
    expect(closable_tag).to_be_visible()

    close_btn = closable_tag.locator('.base-tag__close')
    expect(close_btn).to_be_visible()

    # Click close button
    close_btn.click()
    time.sleep(0.1)
    expect(closable_tag).not_to_be_visible()


def test_theme_switching_light_to_dark(page: Page, test_page_url: str):
    """Test components adapt to light/dark theme switching"""
    page.goto(test_page_url)

    # Get computed style in light theme
    button = page.locator('[data-test="button-primary"]')
    light_bg = page.evaluate("""
        () => getComputedStyle(document.querySelector('[data-test="button-primary"]'))
            .backgroundColor
    """)

    # Switch to dark theme
    page.locator('[data-test="theme-toggle"]').click()
    time.sleep(0.2)  # Wait for CSS transition

    # Check dark theme class applied
    expect(page.locator('html')).to_have_class(lambda classes: 'theme-dark' in classes)

    # Get computed style in dark theme
    dark_bg = page.evaluate("""
        () => getComputedStyle(document.querySelector('[data-test="button-primary"]'))
            .backgroundColor
    """)

    # Colors should be different
    assert light_bg != dark_bg, "Button background should change between themes"


def test_accessibility_focus_indicators(page: Page, test_page_url: str):
    """Test components have visible focus indicators"""
    page.goto(test_page_url)

    button = page.locator('[data-test="button-primary"]')
    button.focus()

    # Check focus-visible styles are applied
    outline = page.evaluate("""
        () => {
            const el = document.querySelector('[data-test="button-primary"]');
            return getComputedStyle(el).outlineWidth;
        }
    """)

    assert outline != '0px', "Button should have visible focus outline"


def test_accessibility_aria_labels(page: Page, test_page_url: str):
    """Test components have proper ARIA labels"""
    page.goto(test_page_url)

    # Close button should have aria-label
    closable_tag = page.locator('[data-test="tag-closable"]')
    close_btn = closable_tag.locator('.base-tag__close')

    aria_label = close_btn.get_attribute('aria-label')
    assert aria_label == 'Close', "Close button should have aria-label"


def test_mobile_touch_targets(page: Page, test_page_url: str):
    """Test mobile touch targets meet 44px minimum"""
    page.goto(test_page_url)

    # Set mobile viewport
    page.set_viewport_size({"width": 375, "height": 667})

    # Test button touch target
    button = page.locator('[data-test="button-medium"]')
    box = button.bounding_box()
    assert box is not None
    assert box['height'] >= 44, "Button should meet 44px touch target on mobile"

    # Test input touch target
    input_field = page.locator('[data-test="input-medium"]')
    box = input_field.bounding_box()
    assert box is not None
    assert box['height'] >= 44, "Input should meet 44px touch target on mobile"

    # Test tab touch target
    tab = page.locator('[data-test="tab-first"]')
    box = tab.bounding_box()
    assert box is not None
    assert box['height'] >= 44, "Tab should meet 44px touch target on mobile"

#!/usr/bin/env python3
"""
Standalone test for CSS Variables and Visual Specification
验证设计 token 系统和视觉规范实现
"""
import os
import re
import sys


class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []

    def test(self, name, condition, message=""):
        """Run a single test"""
        try:
            assert condition, message
            self.passed += 1
            print(f"✓ {name}")
            return True
        except AssertionError as e:
            self.failed += 1
            print(f"✗ {name}")
            if message:
                print(f"  {message}")
            return False

    def summary(self):
        """Print test summary"""
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"Tests: {total} total, {self.passed} passed, {self.failed} failed")
        if self.failed == 0:
            print("✓ All tests passed!")
        return self.failed == 0


def main():
    runner = TestRunner()

    # Test 1: Styles directory exists
    styles_dir = 'dashboard/ui/src/styles'
    runner.test(
        "Styles directory exists",
        os.path.exists(styles_dir) and os.path.isdir(styles_dir),
        f"Directory should exist at {styles_dir}"
    )

    # Test 2: Variables.css exists
    variables_file = 'dashboard/ui/src/styles/variables.css'
    runner.test(
        "variables.css exists",
        os.path.exists(variables_file),
        f"File should exist at {variables_file}"
    )

    # Test 3: Base.css exists
    base_file = 'dashboard/ui/src/styles/base.css'
    runner.test(
        "base.css exists",
        os.path.exists(base_file),
        f"File should exist at {base_file}"
    )

    # Test 4: Utilities.css exists
    utilities_file = 'dashboard/ui/src/styles/utilities.css'
    runner.test(
        "utilities.css exists",
        os.path.exists(utilities_file),
        f"File should exist at {utilities_file}"
    )

    # Test 5: Variables content
    if os.path.exists(variables_file):
        with open(variables_file, 'r', encoding='utf-8') as f:
            variables_content = f.read()

        runner.test(
            "Color system defined",
            all(var in variables_content for var in [
                '--color-canvas:', '--color-surface:', '--color-ink:',
                '--color-accent:', '--color-up:', '--color-down:'
            ]),
            "Should define all core color variables"
        )

        runner.test(
            "Spacing system defined",
            all(var in variables_content for var in [
                '--spacing-xs:', '--spacing-sm:', '--spacing-md:',
                '--spacing-lg:', '--spacing-xl:'
            ]),
            "Should define spacing scale"
        )

        runner.test(
            "Border radius system defined",
            all(var in variables_content for var in [
                '--radius-sm:', '--radius-md:', '--radius-lg:'
            ]),
            "Should define border radius scale"
        )

        runner.test(
            "Duration system defined",
            all(var in variables_content for var in [
                '--duration-fast:', '--duration-normal:', '--duration-slow:'
            ]),
            "Should define animation durations"
        )

        runner.test(
            "Shadow system defined",
            all(var in variables_content for var in [
                '--shadow-sm:', '--shadow-md:', '--shadow-lg:'
            ]),
            "Should define shadow scale"
        )

        runner.test(
            "Layout constants defined",
            all(var in variables_content for var in [
                '--sidebar-width:', '--topbar-height:', '--touch-target-min:'
            ]),
            "Should define layout constants"
        )

        runner.test(
            "Font system defined",
            all(var in variables_content for var in [
                '--font-family-base:', '--font-size-xs:', '--font-size-base:',
                '--font-weight-normal:'
            ]),
            "Should define font system"
        )

        runner.test(
            "Theme classes exist",
            ('.theme-dark' in variables_content or '[data-theme="dark"]' in variables_content)
            and '.theme-light' in variables_content,
            "Should define light and dark theme classes"
        )

        runner.test(
            "AI content colors defined",
            '--color-ai-bg:' in variables_content and '--color-ai-border:' in variables_content,
            "Should define AI content background colors"
        )

        # Check touch target size
        match = re.search(r'--touch-target-min:\s*(\d+)px', variables_content)
        if match:
            touch_target = int(match.group(1))
            runner.test(
                "Touch target meets minimum size (44px)",
                touch_target >= 44,
                f"Touch target should be at least 44px, got {touch_target}px"
            )

    # Test 6: Base CSS content
    if os.path.exists(base_file):
        with open(base_file, 'r', encoding='utf-8') as f:
            base_content = f.read()

        runner.test(
            "Box-sizing reset included",
            'box-sizing: border-box' in base_content,
            "Should include box-sizing reset"
        )

        runner.test(
            "Body styles defined",
            'body {' in base_content and 'background: var(--color-canvas)' in base_content,
            "Should define body styles using design tokens"
        )

        runner.test(
            "Focus styles defined",
            ':focus-visible' in base_content,
            "Should define accessible focus styles"
        )

        runner.test(
            "Screen reader class defined",
            '.sr-only' in base_content,
            "Should define .sr-only for accessibility"
        )

        runner.test(
            "Responsive or accessibility media queries",
            '@media' in base_content,
            "Should include media queries"
        )

    # Test 7: Utilities CSS content
    if os.path.exists(utilities_file):
        with open(utilities_file, 'r', encoding='utf-8') as f:
            utilities_content = f.read()

        runner.test(
            "Flex utilities defined",
            all(cls in utilities_content for cls in [
                '.flex', '.flex-col', '.items-center', '.justify-between'
            ]),
            "Should define flex layout utilities"
        )

        runner.test(
            "Spacing utilities defined",
            '.gap-sm' in utilities_content or '.gap-md' in utilities_content,
            "Should define spacing utilities"
        )

        runner.test(
            "Text utilities defined",
            '.text-center' in utilities_content and
            ('.text-sm' in utilities_content or '.text-base' in utilities_content),
            "Should define text utilities"
        )

        runner.test(
            "Color utilities defined",
            '.text-accent' in utilities_content and '.bg-surface' in utilities_content,
            "Should define color utilities"
        )

        runner.test(
            "Border radius utilities defined",
            '.rounded-md' in utilities_content or '.rounded-lg' in utilities_content,
            "Should define border radius utilities"
        )

        runner.test(
            "Shadow utilities defined",
            '.shadow-md' in utilities_content or '.shadow-lg' in utilities_content,
            "Should define shadow utilities"
        )

        runner.test(
            "Responsive utilities defined",
            '.mobile-only' in utilities_content and '.desktop-only' in utilities_content,
            "Should define responsive visibility utilities"
        )

        runner.test(
            "Animation utilities defined",
            '@keyframes' in utilities_content,
            "Should define animation keyframes"
        )

    # Test 8: Main styles.css imports
    main_styles = 'dashboard/ui/src/styles.css'
    if os.path.exists(main_styles):
        with open(main_styles, 'r', encoding='utf-8') as f:
            main_content = f.read()

        runner.test(
            "Main styles imports variables.css",
            "@import './styles/variables.css'" in main_content,
            "Should import variables.css"
        )

        runner.test(
            "Main styles imports base.css",
            "@import './styles/base.css'" in main_content,
            "Should import base.css"
        )

        runner.test(
            "Main styles imports utilities.css",
            "@import './styles/utilities.css'" in main_content,
            "Should import utilities.css"
        )

        runner.test(
            "Legacy variable aliases defined",
            all(alias in main_content for alias in [
                '--canvas: var(--color-canvas)',
                '--surface: var(--color-surface)',
                '--ink: var(--color-ink)',
                '--accent: var(--color-accent)'
            ]),
            "Should define legacy variable aliases for backward compatibility"
        )

    # Print summary
    success = runner.summary()
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

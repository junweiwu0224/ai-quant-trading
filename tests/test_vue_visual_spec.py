"""
Test CSS Variables and Visual Specification
验证设计 token 系统和视觉规范实现
"""
import os
import re


def test_styles_directory_exists():
    """验证 styles 目录已创建"""
    styles_dir = 'dashboard/ui/src/styles'
    assert os.path.exists(styles_dir), f"Styles directory should exist at {styles_dir}"
    assert os.path.isdir(styles_dir), f"{styles_dir} should be a directory"


def test_variables_css_exists():
    """验证 variables.css 文件存在"""
    variables_file = 'dashboard/ui/src/styles/variables.css'
    assert os.path.exists(variables_file), f"Variables file should exist at {variables_file}"


def test_base_css_exists():
    """验证 base.css 文件存在"""
    base_file = 'dashboard/ui/src/styles/base.css'
    assert os.path.exists(base_file), f"Base file should exist at {base_file}"


def test_utilities_css_exists():
    """验证 utilities.css 文件存在"""
    utilities_file = 'dashboard/ui/src/styles/utilities.css'
    assert os.path.exists(utilities_file), f"Utilities file should exist at {utilities_file}"


def test_variables_css_content():
    """验证 variables.css 包含必需的设计 token"""
    variables_file = 'dashboard/ui/src/styles/variables.css'
    with open(variables_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查颜色系统
    assert '--color-canvas:' in content, "Should define --color-canvas"
    assert '--color-surface:' in content, "Should define --color-surface"
    assert '--color-ink:' in content, "Should define --color-ink"
    assert '--color-accent:' in content, "Should define --color-accent"
    assert '--color-up:' in content, "Should define --color-up"
    assert '--color-down:' in content, "Should define --color-down"

    # 检查间距系统
    assert '--spacing-xs:' in content, "Should define --spacing-xs"
    assert '--spacing-sm:' in content, "Should define --spacing-sm"
    assert '--spacing-md:' in content, "Should define --spacing-md"
    assert '--spacing-lg:' in content, "Should define --spacing-lg"
    assert '--spacing-xl:' in content, "Should define --spacing-xl"

    # 检查圆角系统
    assert '--radius-sm:' in content, "Should define --radius-sm"
    assert '--radius-md:' in content, "Should define --radius-md"
    assert '--radius-lg:' in content, "Should define --radius-lg"

    # 检查动画时长
    assert '--duration-fast:' in content, "Should define --duration-fast"
    assert '--duration-normal:' in content, "Should define --duration-normal"
    assert '--duration-slow:' in content, "Should define --duration-slow"

    # 检查阴影系统
    assert '--shadow-sm:' in content, "Should define --shadow-sm"
    assert '--shadow-md:' in content, "Should define --shadow-md"
    assert '--shadow-lg:' in content, "Should define --shadow-lg"

    # 检查布局常量
    assert '--sidebar-width:' in content, "Should define --sidebar-width"
    assert '--topbar-height:' in content, "Should define --topbar-height"
    assert '--touch-target-min:' in content, "Should define --touch-target-min"

    # 检查字体系统
    assert '--font-family-base:' in content, "Should define --font-family-base"
    assert '--font-size-xs:' in content, "Should define --font-size-xs"
    assert '--font-size-base:' in content, "Should define --font-size-base"
    assert '--font-weight-normal:' in content, "Should define --font-weight-normal"


def test_theme_classes_exist():
    """验证主题类存在"""
    variables_file = 'dashboard/ui/src/styles/variables.css'
    with open(variables_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查深色主题
    assert '.theme-dark' in content or '[data-theme="dark"]' in content, \
        "Should define dark theme class"

    # 检查浅色主题
    assert '.theme-light' in content, "Should define light theme class"


def test_base_css_resets():
    """验证 base.css 包含必要的重置样式"""
    base_file = 'dashboard/ui/src/styles/base.css'
    with open(base_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查基础重置
    assert 'box-sizing: border-box' in content, "Should include box-sizing reset"
    assert 'body {' in content, "Should define body styles"
    assert 'background: var(--color-canvas)' in content, "Body should use canvas color"

    # 检查焦点样式
    assert ':focus-visible' in content, "Should define focus-visible styles"

    # 检查辅助功能
    assert '.sr-only' in content, "Should define screen reader only class"

    # 检查响应式
    assert '@media (max-width:' in content or '@media (prefers-reduced-motion:' in content, \
        "Should include responsive or accessibility media queries"


def test_utilities_css_classes():
    """验证 utilities.css 包含工具类"""
    utilities_file = 'dashboard/ui/src/styles/utilities.css'
    with open(utilities_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查 Flex 工具类
    assert '.flex' in content, "Should define .flex"
    assert '.flex-col' in content, "Should define .flex-col"
    assert '.items-center' in content, "Should define .items-center"
    assert '.justify-between' in content, "Should define .justify-between"

    # 检查间距工具类
    assert '.gap-sm' in content or '.gap-md' in content, "Should define gap utilities"
    assert '.p-md' in content or '.p-sm' in content, "Should define padding utilities"

    # 检查文本工具类
    assert '.text-center' in content, "Should define .text-center"
    assert '.text-sm' in content or '.text-base' in content, "Should define text size utilities"

    # 检查颜色工具类
    assert '.text-accent' in content, "Should define .text-accent"
    assert '.bg-surface' in content, "Should define .bg-surface"

    # 检查圆角工具类
    assert '.rounded-md' in content or '.rounded-lg' in content, "Should define border radius utilities"

    # 检查阴影工具类
    assert '.shadow-md' in content or '.shadow-lg' in content, "Should define shadow utilities"


def test_main_styles_imports():
    """验证主 styles.css 导入了模块化文件"""
    main_styles = 'dashboard/ui/src/styles.css'
    with open(main_styles, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查导入语句
    assert "@import './styles/variables.css'" in content, \
        "Should import variables.css"
    assert "@import './styles/base.css'" in content, \
        "Should import base.css"
    assert "@import './styles/utilities.css'" in content, \
        "Should import utilities.css"


def test_legacy_variable_aliases():
    """验证主 styles.css 包含向后兼容的变量别名"""
    main_styles = 'dashboard/ui/src/styles.css'
    with open(main_styles, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查旧变量名映射到新变量
    assert '--canvas: var(--color-canvas)' in content, \
        "Should alias --canvas to --color-canvas"
    assert '--surface: var(--color-surface)' in content, \
        "Should alias --surface to --color-surface"
    assert '--ink: var(--color-ink)' in content, \
        "Should alias --ink to --color-ink"
    assert '--accent: var(--color-accent)' in content, \
        "Should alias --accent to --color-accent"


def test_touch_target_minimum():
    """验证触摸目标最小尺寸符合要求"""
    variables_file = 'dashboard/ui/src/styles/variables.css'
    with open(variables_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取 touch-target-min 值
    match = re.search(r'--touch-target-min:\s*(\d+)px', content)
    assert match, "Should define --touch-target-min"

    touch_target = int(match.group(1))
    assert touch_target >= 44, f"Touch target should be at least 44px, got {touch_target}px"


def test_dark_theme_colors():
    """验证深色主题颜色定义"""
    variables_file = 'dashboard/ui/src/styles/variables.css'
    with open(variables_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 查找深色主题部分
    dark_theme_pattern = r'\.theme-dark[^{]*{([^}]+)}'
    match = re.search(dark_theme_pattern, content, re.DOTALL)

    if not match:
        # 尝试查找 [data-theme="dark"]
        dark_theme_pattern = r'\[data-theme="dark"\][^{]*{([^}]+)}'
        match = re.search(dark_theme_pattern, content, re.DOTALL)

    assert match, "Should define dark theme colors"

    dark_theme_content = match.group(1)
    assert '--color-canvas:' in dark_theme_content, "Dark theme should define --color-canvas"
    assert '--color-surface:' in dark_theme_content, "Dark theme should define --color-surface"


def test_ai_content_background():
    """验证 AI 内容背景色定义（用于区分 AI 生成内容）"""
    variables_file = 'dashboard/ui/src/styles/variables.css'
    with open(variables_file, 'r', encoding='utf-8') as f:
        content = f.read()

    assert '--color-ai-bg:' in content, "Should define --color-ai-bg"
    assert '--color-ai-border:' in content, "Should define --color-ai-border"


def test_responsive_utilities():
    """验证响应式工具类"""
    utilities_file = 'dashboard/ui/src/styles/utilities.css'
    with open(utilities_file, 'r', encoding='utf-8') as f:
        content = f.read()

    assert '.mobile-only' in content, "Should define .mobile-only"
    assert '.desktop-only' in content, "Should define .desktop-only"


def test_animation_utilities():
    """验证动画工具类"""
    utilities_file = 'dashboard/ui/src/styles/utilities.css'
    with open(utilities_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查动画定义
    assert '@keyframes' in content, "Should define keyframe animations"
    assert 'spin' in content or 'fade' in content or 'pulse' in content, \
        "Should define animation keyframes"


if __name__ == '__main__':
    import pytest
    pytest.main([__file__, '-v'])

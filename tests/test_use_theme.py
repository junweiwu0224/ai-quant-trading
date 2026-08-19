def test_use_theme_composable_exists():
    """验证 useTheme composable 已创建"""
    import os
    assert os.path.exists('dashboard/ui/src/composables/useTheme.ts')

def test_use_theme_exports():
    """验证 useTheme 导出正确的接口"""
    content = open('dashboard/ui/src/composables/useTheme.ts').read()

    assert 'export function useTheme()' in content
    assert 'setTheme' in content
    assert 'toggleTheme' in content
    assert 'theme.value' in content

def test_use_theme_class_names():
    """验证主题由 App Store 的 data-theme 属性统一应用"""
    content = open('dashboard/ui/src/stores/app.ts').read()

    assert "document.documentElement.dataset.theme" in content
    assert "'dark'" in content
    assert "'light'" in content


def test_use_theme_storage_key():
    """验证 App Store 使用正确的 localStorage key"""
    content = open('dashboard/ui/src/stores/app.ts').read()

    assert 'quant-theme' in content
    assert 'localStorage' in content

def test_use_theme_system_preference():
    """验证监听系统主题偏好"""
    content = open('dashboard/ui/src/composables/useTheme.ts').read()

    assert 'prefers-color-scheme' in content
    assert 'matchMedia' in content
    assert 'addEventListener' in content

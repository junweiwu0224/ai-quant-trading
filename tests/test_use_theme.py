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
    """验证主题类名与 Task 1 约定一致"""
    content = open('dashboard/ui/src/composables/useTheme.ts').read()

    # 必须使用 .theme-light 和 .theme-dark 类名
    assert 'theme-dark' in content
    assert 'theme-light' in content

def test_use_theme_storage_key():
    """验证使用正确的 localStorage key"""
    content = open('dashboard/ui/src/composables/useTheme.ts').read()

    assert 'quant-theme' in content
    assert 'localStorage' in content

def test_use_theme_system_preference():
    """验证监听系统主题偏好"""
    content = open('dashboard/ui/src/composables/useTheme.ts').read()

    assert 'prefers-color-scheme' in content
    assert 'matchMedia' in content
    assert 'addEventListener' in content

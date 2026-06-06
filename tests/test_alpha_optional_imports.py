import builtins
import importlib
import sys


def test_alpha_package_imports_when_lightgbm_backend_is_unavailable(monkeypatch):
    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "lightgbm":
            raise OSError("libomp.dylib missing")
        return real_import(name, *args, **kwargs)

    for module_name in list(sys.modules):
        if module_name == "alpha" or module_name.startswith("alpha."):
            sys.modules.pop(module_name, None)
    monkeypatch.setattr(builtins, "__import__", guarded_import)

    alpha = importlib.import_module("alpha")

    assert alpha.FeaturePipeline is not None
    assert not alpha.is_model_backend_available("lightgbm")
    assert alpha.get_model_backend_error("lightgbm")

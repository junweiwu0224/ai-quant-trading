from alpha.models.lightgbm_model import (
    LGBConfig,
    LGBModel,
    is_lightgbm_available,
    lightgbm_backend_error,
)
from alpha.models.xgb_model import (
    XGBConfig,
    XGBModel,
    is_xgboost_available,
    xgboost_backend_error,
)
from alpha.models.ensemble_model import EnsembleModel, EnsembleConfig, EnsembleStrategy


def is_model_backend_available(model_type: str = "lightgbm") -> bool:
    if model_type == "lightgbm":
        return is_lightgbm_available()
    if model_type == "xgboost":
        return is_xgboost_available()
    if model_type == "ensemble":
        return is_lightgbm_available() and is_xgboost_available()
    return True


def get_model_backend_error(model_type: str = "lightgbm") -> str:
    if model_type == "lightgbm":
        return lightgbm_backend_error()
    if model_type == "xgboost":
        return xgboost_backend_error()
    if model_type == "ensemble":
        errors = [err for err in (lightgbm_backend_error(), xgboost_backend_error()) if err]
        return " | ".join(errors)
    return ""

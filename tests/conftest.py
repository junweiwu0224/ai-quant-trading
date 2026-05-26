"""共享测试 fixtures"""
import os

os.environ["APP_ENV"] = "test"

import pytest
from fastapi.testclient import TestClient

from dashboard.app import app

os.environ["APP_ENV"] = "test"


@pytest.fixture
def client():
    return TestClient(app)

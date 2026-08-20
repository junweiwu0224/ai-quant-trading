from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v2_compose_and_full_deployment_docs_disable_live() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    commands = (ROOT / "docs" / "commands.md").read_text(encoding="utf-8")
    full_deployment = commands.split("### 全量本地部署（默认）", 1)[1].split("\n## 测试", 1)[0]

    assert "\n  live:\n" not in compose
    assert "scripts/run_live.py" not in compose
    assert "\n  paper:\n" in compose
    assert "\n  backtest:\n" in compose
    assert "scripts/run_paper.py" in compose
    assert "scripts/run_backtest.py" in compose
    assert "V2 Live 当前禁用" in full_deployment
    assert "scripts/run_live.py" in full_deployment
    assert "不作为 Compose 服务启动" in full_deployment
    assert "live 模拟模式" not in full_deployment

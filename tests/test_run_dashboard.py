import os

from click.testing import CliRunner


def test_run_dashboard_sets_qlib_service_url_from_qlib_port(monkeypatch):
    from scripts import run_dashboard

    captured = {}

    def fake_start_qlib_service(qlib_port):
        captured["qlib_port"] = qlib_port
        return None

    def fake_uvicorn_run(app_ref, **kwargs):
        captured["app_ref"] = app_ref
        captured["uvicorn_kwargs"] = kwargs
        captured["service_url"] = os.environ.get("QLIB_SERVICE_URL")

    monkeypatch.delenv("QLIB_SERVICE_URL", raising=False)
    monkeypatch.setattr(run_dashboard, "_start_qlib_service", fake_start_qlib_service)
    monkeypatch.setattr(run_dashboard.uvicorn, "run", fake_uvicorn_run)

    result = CliRunner().invoke(
        run_dashboard.main,
        ["--host", "127.0.0.1", "--port", "8311", "--qlib-port", "8314"],
    )

    assert result.exit_code == 0, result.output
    assert captured["qlib_port"] == 8314
    assert captured["app_ref"] == "dashboard.app:app"
    assert captured["service_url"] == "http://127.0.0.1:8314"

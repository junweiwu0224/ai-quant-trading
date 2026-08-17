def test_scheduler_runs_qlib_daily_sync_after_watchlist_sync(monkeypatch):
    from data.scheduler.scheduler import DataScheduler

    class EmptyStorage:
        def get_all_watchlist_codes(self):
            return []

    calls = []

    def fake_sync_qlib_daily(**kwargs):
        calls.append(kwargs)
        return type(
            "Summary",
            (),
            {
                "success": True,
                "success_count": 3,
                "fail_count": 0,
                "prediction_success": True,
                "prediction_total": 3,
            },
        )()

    monkeypatch.setattr("data.scheduler.scheduler.sync_qlib_daily", fake_sync_qlib_daily)

    scheduler = DataScheduler(storage=EmptyStorage())
    scheduler.sync_qlib_coverage()

    assert calls == [
        {
            "storage": scheduler._storage,
            "adapter": scheduler._provider,
            "generate_predictions_cache": True,
            "min_success": 2,
            "status_source": "scheduler",
        }
    ]


def test_scheduler_registers_qlib_job():
    from data.scheduler.scheduler import DataScheduler

    class FakeScheduler:
        def __init__(self):
            self.running = False
            self.jobs = []

        def add_job(self, func, trigger, id, name):
            self.jobs.append({"func": func, "trigger": trigger, "id": id, "name": name})

        def start(self):
            self.running = True

    class EmptyStorage:
        pass

    fake_scheduler = FakeScheduler()
    scheduler = DataScheduler(storage=EmptyStorage())
    scheduler._scheduler = fake_scheduler

    scheduler.start()

    job_ids = [job["id"] for job in fake_scheduler.jobs]
    assert job_ids == ["daily_sync", "qlib_daily_sync", "daily_research"]
    assert fake_scheduler.jobs[1]["func"] == scheduler.sync_qlib_coverage
    assert fake_scheduler.jobs[1]["name"] == "每日 AI 信号覆盖池同步"
    assert "Qlib" not in fake_scheduler.jobs[1]["name"]
    assert fake_scheduler.jobs[2]["func"] == scheduler.run_daily_research
    assert fake_scheduler.jobs[2]["name"] == "每日情报投研与日报"


def test_scheduler_sync_all_uses_full_daily_sync(monkeypatch):
    from data.scheduler.scheduler import DataScheduler

    calls = []

    def fake_sync_full_stock_daily(**kwargs):
        calls.append(kwargs)
        return type(
            "Summary",
            (),
            {
                "success_count": 2,
                "fail_count": 0,
                "target_count": 2,
                "coverage": {"daily_covered": 2, "stock_count": 2},
            },
        )()

    monkeypatch.setattr("data.scheduler.scheduler.sync_full_stock_daily", fake_sync_full_stock_daily)

    scheduler = DataScheduler(storage=object())
    summary = scheduler.sync_all()

    assert summary.success_count == 2
    assert calls == [{"storage": scheduler._storage}]


def test_scheduler_daily_research_is_workspace_scoped(monkeypatch):
    from types import SimpleNamespace

    from data.scheduler.scheduler import DataScheduler

    class Storage:
        def get_all_watchlist_codes(self):
            return [
                ("workspace-b", ["600002"]),
                ("workspace-a", ["600001", "600001"]),
                ("", ["600003"]),
            ]

    class FakeEvidence:
        def __init__(self, path):
            self.path = path

        def close(self):
            pass

    class FakeOutbox:
        def __init__(self, path):
            self.path = path

        def close(self):
            pass

    repositories = []

    class FakeRepository:
        @classmethod
        def for_workspace(cls, workspace_id, *, base_dir):
            repository = SimpleNamespace(workspace_id=workspace_id, base_dir=base_dir)
            repositories.append(repository)
            return repository

    services = []

    class FakeDailyService:
        def __init__(self, evidence_store, repository, outbox, *, workspace_id, owner):
            self.evidence_store = evidence_store
            self.outbox = outbox
            self.workspace_id = workspace_id
            self.repository = repository
            self.owner = owner
            services.append(self)

        async def run(self, *, watchlist, run_key):
            self.watchlist = list(watchlist)
            self.run_key = run_key
            return SimpleNamespace(brief=SimpleNamespace(report_count=len(watchlist)))

    monkeypatch.setattr("agentic.daily_run.DailyResearchRunService", FakeDailyService)
    monkeypatch.setattr("agentic.repository.AgenticRepository", FakeRepository)
    monkeypatch.setattr("data.evidence.store.SQLiteEvidenceStore", FakeEvidence)
    monkeypatch.setattr("engine.events.outbox.SQLiteOutbox", FakeOutbox)

    result = DataScheduler(storage=Storage()).run_daily_research()

    assert len(result) == 3
    assert {item.workspace_id for item in repositories} == {"workspace-a", "workspace-b", "default"}
    by_workspace = {service.workspace_id: service for service in services}
    assert by_workspace["workspace-a"].watchlist == ["600001"]
    assert by_workspace["workspace-b"].watchlist == ["600002"]
    assert by_workspace["default"].watchlist == ["600003"]
    assert by_workspace["workspace-a"].run_key.startswith("workspace:workspace-a:daily:")
    assert by_workspace["workspace-b"].run_key.startswith("workspace:workspace-b:daily:")
    assert by_workspace["default"].run_key.startswith("daily:")

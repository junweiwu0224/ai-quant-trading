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
    assert job_ids == ["daily_sync", "qlib_daily_sync"]
    assert fake_scheduler.jobs[1]["func"] == scheduler.sync_qlib_coverage

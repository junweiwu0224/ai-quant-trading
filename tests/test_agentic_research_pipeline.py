from agentic.repository import AgenticRepository
from agentic.research_pipeline import ResearchPipeline


def test_research_pipeline_generates_five_role_report(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    pipeline = ResearchPipeline(repo)

    job = pipeline.run(code="605066.SH", context={"signal_score": 0.72, "theme": "grid equipment"})
    persisted = repo.get_research_job(job.id)

    assert job.status == "completed"
    assert job.code == "605066"
    assert job.roles == ("signal", "market", "theme", "bear", "decision")
    assert job.final_report["decision"] == "paper_candidate"
    assert job.final_report["signal_score"] == 0.72
    assert "qlib_score" not in job.final_report
    assert "qlib" not in job.final_report["roles"]
    assert persisted == job


def test_research_pipeline_accepts_legacy_qlib_score_as_input_alias(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    pipeline = ResearchPipeline(repo)

    job = pipeline.run(code="605066.SH", context={"qlib_score": 0.72, "theme": "grid equipment"})

    assert job.final_report["signal_score"] == 0.72
    assert job.final_report["input_aliases"] == {"qlib_score": "signal_score"}
    assert "qlib_score" not in job.final_report
    assert "qlib" not in job.final_report["roles"]


def test_research_pipeline_observes_when_signal_score_is_below_threshold(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    pipeline = ResearchPipeline(repo)

    job = pipeline.run(code="000001", context={"signal_score": 0.59, "theme": "banking"})

    assert job.status == "completed"
    assert job.final_report["decision"] == "observe"
    assert job.final_report["roles"]["decision"]["rationale"] == "signal_score below paper threshold"

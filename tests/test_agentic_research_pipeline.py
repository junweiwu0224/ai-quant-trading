from agentic.repository import AgenticRepository
from agentic.research_pipeline import ResearchPipeline


def test_research_pipeline_generates_five_role_report(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    pipeline = ResearchPipeline(repo)

    job = pipeline.run(code="605066.SH", context={"qlib_score": 0.72, "theme": "grid equipment"})
    persisted = repo.get_research_job(job.id)

    assert job.status == "completed"
    assert job.code == "605066"
    assert job.roles == ("qlib", "market", "theme", "bear", "decision")
    assert job.final_report["decision"] == "paper_candidate"
    assert job.final_report["qlib_score"] == 0.72
    assert persisted == job


def test_research_pipeline_observes_when_qlib_score_is_below_threshold(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    pipeline = ResearchPipeline(repo)

    job = pipeline.run(code="000001", context={"qlib_score": 0.59, "theme": "banking"})

    assert job.status == "completed"
    assert job.final_report["decision"] == "observe"
    assert job.final_report["roles"]["decision"]["rationale"] == "qlib_score below paper threshold"

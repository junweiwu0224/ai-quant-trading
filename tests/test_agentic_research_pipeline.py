from agentic.repository import AgenticRepository
from agentic.research_pipeline import ResearchPipeline


def test_research_pipeline_generates_five_role_report(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    pipeline = ResearchPipeline(repo)

    job = pipeline.run(
        code="605066.SH",
        context={
            "signal_score": 0.72,
            "theme": "grid equipment",
            "signal_validation": {"confidence": "validated_positive", "sample_days": 42},
        },
    )
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

    job = pipeline.run(
        code="605066.SH",
        context={
            "qlib_score": 0.72,
            "theme": "grid equipment",
            "signal_validation": {"confidence": "validated_positive", "sample_days": 42},
        },
    )

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


def test_research_pipeline_does_not_promote_unverified_ai_signal(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    pipeline = ResearchPipeline(repo)

    job = pipeline.run(
        code="605066.SH",
        context={
            "signal_score": 0.92,
            "theme": "grid equipment",
            "signal_validation": {"confidence": "unverified", "sample_days": 0},
        },
    )

    assert job.final_report["decision"] == "observe"
    assert job.final_report["signal_validation"]["confidence"] == "unverified"
    assert job.final_report["roles"]["decision"]["rationale"] == "AI未验证 · 未验证 · 样本 0 天"
    assert "AI signal is not validated" not in job.final_report["roles"]["decision"]["rationale"]
    assert "AI未验证" in job.final_report["roles"]["bear"]["risk"]


def test_research_pipeline_does_not_promote_with_tiny_validation_sample(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    pipeline = ResearchPipeline(repo)

    job = pipeline.run(
        code="605066.SH",
        context={
            "signal_score": 0.92,
            "theme": "grid equipment",
            "signal_validation": {"confidence": "validated_neutral", "sample_days": 1},
        },
    )

    assert job.final_report["decision"] == "observe"
    assert job.final_report["signal_validation"]["sample_days"] == 1
    assert job.final_report["roles"]["decision"]["rationale"] == "AI验证样本不足 · 验证中性 · 样本 1/20 天"
    assert "AI signal validation sample is insufficient" not in job.final_report["roles"]["decision"]["rationale"]
    assert "AI验证样本不足" in job.final_report["roles"]["bear"]["risk"]


def test_research_pipeline_legacy_qlib_score_without_validation_stays_observe(tmp_path):
    repo = AgenticRepository(tmp_path / "agentic.db")
    pipeline = ResearchPipeline(repo)

    job = pipeline.run(code="605066.SH", context={"qlib_score": 0.92, "theme": "grid equipment"})

    assert job.final_report["decision"] == "observe"
    assert job.final_report["input_aliases"] == {"qlib_score": "signal_score"}
    assert job.final_report["signal_validation"]["confidence"] == "unverified"
    assert "qlib_score" not in job.final_report

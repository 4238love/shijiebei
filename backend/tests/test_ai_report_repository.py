from app.ai_report_repository import InMemoryAIReportRepository


def test_in_memory_ai_report_repository_saves_and_retrieves_report():
    repository = InMemoryAIReportRepository()

    report_id = repository.save({"provider_name": "gpt", "content": "analysis"})

    assert repository.get(report_id) == {
        "id": report_id,
        "provider_name": "gpt",
        "content": "analysis",
    }


def test_in_memory_ai_report_repository_returns_none_for_missing_report():
    repository = InMemoryAIReportRepository()

    assert repository.get("missing") is None

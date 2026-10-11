import json

from fastapi.testclient import TestClient

from silki_ai.clova_test_app import app, save_transcript


def test_clova_test_page_is_available_without_database() -> None:
    with TestClient(app) as client:
        response = client.get("/clova-test")

    assert response.status_code == 200
    assert "Silki CLOVA Check" in response.text
    assert "/clova-test/ws" in response.text


def test_save_transcript_writes_jsonl_record(tmp_path) -> None:
    transcript_path = tmp_path / "clova_transcripts.jsonl"

    save_transcript(session_id="session-1", text="아이스 아메리카노", path=transcript_path)

    assert json.loads(transcript_path.read_text(encoding="utf-8")) == {
        "recordedAt": json.loads(transcript_path.read_text(encoding="utf-8"))["recordedAt"],
        "sessionId": "session-1",
        "text": "아이스 아메리카노",
    }
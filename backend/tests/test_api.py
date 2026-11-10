from pathlib import Path

from fastapi.testclient import TestClient

from app import main


client = TestClient(main.app)


def test_health_reports_current_api_version():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "JARVIS AI Video Studio",
        "version": "0.7.0",
    }


def test_srt_time_formats_milliseconds():
    assert main.srt_time(0) == "00:00:00,000"
    assert main.srt_time(65.432) == "00:01:05,432"
    assert main.srt_time(3661.007) == "01:01:01,007"


def test_upload_rejects_unsupported_file_type():
    response = client.post(
        "/api/upload",
        files={"file": ("notes.txt", b"not a video", "text/plain")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Unsupported video format"


def test_trim_rejects_zero_duration_before_running_ffmpeg(tmp_path, monkeypatch):
    source = tmp_path / "sample.mp4"
    source.write_bytes(b"placeholder")
    monkeypatch.setattr(main, "MEDIA", tmp_path)

    response = client.post(
        "/api/export/trim",
        json={"filename": source.name, "start": 0, "duration": 0},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Duration must be between 0 and 3600 seconds"


def test_timeline_requires_at_least_two_clips():
    response = client.post(
        "/api/export/timeline",
        json={"clips": [{"filename": "one.mp4", "start": 0, "end": 1}]},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Timeline needs between 2 and 20 clips"

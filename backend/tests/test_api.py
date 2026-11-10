from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import main


client = TestClient(main.app)


def test_health_reports_current_api_version():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "JARVIS AI Video Studio",
        "version": "0.12.0",
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



def test_waveform_reports_video_without_audio(tmp_path, monkeypatch):
    source = tmp_path / "silent.mp4"
    source.write_bytes(b"placeholder")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    monkeypatch.setattr(main, "run_ffprobe", lambda _source: {
        "format": {"duration": "12"}, "streams": [{"codec_type": "video"}]
    })

    response = client.get(f"/api/video/{source.name}/waveform")

    assert response.status_code == 200
    assert response.json()["has_audio"] is False
    assert response.json()["samples"] == []



def test_audio_mix_rejects_volume_out_of_range(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    music = tmp_path / "music.mp3"
    source.write_bytes(b"video")
    music.write_bytes(b"audio")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    monkeypatch.setattr(main, "run_ffprobe", lambda _source: {
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        "format": {"duration": "10"},
    })

    response = client.post("/api/export/audio-mix", json={
        "filename": source.name, "audio_filename": music.name,
        "music_volume": 3, "original_volume": 1,
    })

    assert response.status_code == 400
    assert response.json()["detail"] == "Audio volume must be between 0 and 2"


def test_audio_upload_rejects_video_file():
    response = client.post(
        "/api/upload/audio",
        files={"file": ("clip.mp4", b"not audio", "video/mp4")},
    )

    assert response.status_code == 415
    assert response.json()["detail"] == "Unsupported audio format"



def test_text_overlay_rejects_empty_text_before_ffmpeg(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    response = client.post("/api/export/text", json={
        "filename": source.name, "text": "   "
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Overlay text cannot be empty"


def test_text_overlay_rejects_invalid_position_before_ffmpeg(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    response = client.post("/api/export/text", json={
        "filename": source.name, "text": "Hello", "position": "outside"
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported text position"


def test_text_overlay_rejects_font_size_out_of_range(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    response = client.post("/api/export/text", json={
        "filename": source.name, "text": "Hello", "font_size": 120
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Font size must be between 16 and 96"


def test_text_overlay_renders_and_cleans_temporary_text_file(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    monkeypatch.setattr(main, "run_ffprobe", lambda _source: {
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        "format": {"duration": "5"},
    })
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        text_path = next(tmp_path.glob("overlay-*.txt"))
        captured["text"] = text_path.read_text(encoding="utf-8")
        Path(command[-1]).write_bytes(b"rendered")
        return None

    monkeypatch.setattr(main.subprocess, "run", fake_run)
    response = client.post("/api/export/text", json={
        "filename": source.name, "text": "नमस्ते JARVIS",
        "position": "bottom-right", "font_size": 48,
    })

    assert response.status_code == 200
    assert response.json()["filename"].endswith(".mp4")
    assert captured["text"] == "नमस्ते JARVIS"
    assert "expansion=none" in captured["command"][captured["command"].index("-vf") + 1]
    assert not list(tmp_path.glob("overlay-*.txt"))


def test_fade_rejects_negative_duration_before_ffmpeg(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    monkeypatch.setattr(main, "run_ffprobe", lambda _source: {
        "streams": [{"codec_type": "video"}], "format": {"duration": "10"}
    })
    response = client.post("/api/export/fade", json={
        "filename": source.name, "fade_in": -1, "fade_out": 0
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Fade durations cannot be negative"


def test_fade_rejects_combined_duration_longer_than_video(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    monkeypatch.setattr(main, "run_ffprobe", lambda _source: {
        "streams": [{"codec_type": "video"}], "format": {"duration": "10"}
    })
    response = client.post("/api/export/fade", json={
        "filename": source.name, "fade_in": 6, "fade_out": 5
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Combined fade durations cannot exceed video duration"


def test_fade_requires_at_least_one_effect(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    monkeypatch.setattr(main, "run_ffprobe", lambda _source: {
        "streams": [{"codec_type": "video"}], "format": {"duration": "10"}
    })
    response = client.post("/api/export/fade", json={
        "filename": source.name, "fade_in": 0, "fade_out": 0
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Set fade-in or fade-out duration"


def test_fade_builds_video_filter_for_silent_video(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    monkeypatch.setattr(main, "run_ffprobe", lambda _source: {
        "streams": [{"codec_type": "video"}], "format": {"duration": "10"}
    })
    captured = {}
    def fake_run(command, **kwargs):
        captured["command"] = command
        Path(command[-1]).write_bytes(b"rendered")
    monkeypatch.setattr(main.subprocess, "run", fake_run)
    response = client.post("/api/export/fade", json={
        "filename": source.name, "fade_in": 1.5, "fade_out": 2
    })
    assert response.status_code == 200
    graph = captured["command"][captured["command"].index("-filter_complex") + 1]
    assert "fade=t=in:st=0:d=1.5" in graph
    assert "fade=t=out:st=8.0:d=2.0" in graph
    assert "[a]" not in graph

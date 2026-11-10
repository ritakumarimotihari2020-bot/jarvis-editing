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
        "version": "0.19.0",
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


def test_fade_applies_matching_audio_filters_when_audio_exists(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    monkeypatch.setattr(main, "run_ffprobe", lambda _source: {
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        "format": {"duration": "8"},
    })
    captured = {}
    def fake_run(command, **kwargs):
        captured["command"] = command
        Path(command[-1]).write_bytes(b"rendered")
    monkeypatch.setattr(main.subprocess, "run", fake_run)
    response = client.post("/api/export/fade", json={
        "filename": source.name, "fade_in": 1, "fade_out": 1
    })
    assert response.status_code == 200
    graph = captured["command"][captured["command"].index("-filter_complex") + 1]
    assert "afade=t=in:st=0:d=1.0" in graph
    assert "afade=t=out:st=7.0:d=1.0" in graph
    assert "[a]" in graph



def test_transition_export_rejects_unsupported_transition():
    response = client.post("/api/export/timeline-transition", json={
        "clips": [{"filename": "a.mp4", "start": 0, "end": 2},
                  {"filename": "b.mp4", "start": 0, "end": 2}],
        "transition": "explode",
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported transition type"


def test_transition_export_rejects_duration_out_of_range():
    response = client.post("/api/export/timeline-transition", json={
        "clips": [{"filename": "a.mp4", "start": 0, "end": 2},
                  {"filename": "b.mp4", "start": 0, "end": 2}],
        "transition": "fade", "transition_duration": 5,
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Transition duration must be between 0.1 and 3 seconds"


def test_transition_export_rejects_too_short_clip(tmp_path, monkeypatch):
    source = tmp_path / "short.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    monkeypatch.setattr(main, "run_ffprobe", lambda _source: {
        "streams": [{"codec_type": "video"}], "format": {"duration": "1"}
    })
    response = client.post("/api/export/timeline-transition", json={
        "clips": [{"filename": source.name, "start": 0, "end": 1},
                  {"filename": source.name, "start": 0, "end": 1}],
        "transition": "fade", "transition_duration": 1,
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "Each selected clip must be longer than the transition"


def test_transition_export_builds_video_and_audio_crossfade_graph(tmp_path, monkeypatch):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(main, "MEDIA", tmp_path)
    monkeypatch.setattr(main, "run_ffprobe", lambda _source: {
        "streams": [{"codec_type": "video"}, {"codec_type": "audio"}],
        "format": {"duration": "5"},
    })
    captured = {}
    def fake_run(command, **kwargs):
        captured.setdefault("commands", []).append(command)
        Path(command[-1]).write_bytes(b"rendered")
    monkeypatch.setattr(main.subprocess, "run", fake_run)
    response = client.post("/api/export/timeline-transition", json={
        "clips": [{"filename": source.name, "start": 0, "end": 4},
                  {"filename": source.name, "start": 0, "end": 4},
                  {"filename": source.name, "start": 0, "end": 4}],
        "transition": "dissolve", "transition_duration": 1,
    })
    assert response.status_code == 200
    graph = captured["commands"][-1][captured["commands"][-1].index("-filter_complex") + 1]
    assert graph.count("xfade=transition=dissolve") == 2
    assert graph.count("acrossfade=d=1.0") == 2
    assert response.json()["clips"] == 3
    assert not list(tmp_path.glob("transition-*.mp4"))


def test_projects_can_be_saved_loaded_and_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PROJECTS", tmp_path)
    saved = client.post("/api/projects", json={
        "name": "Travel edit",
        "state": {"timeline_files": [], "timeline_transition": "dissolve"}
    })
    assert saved.status_code == 200
    project_id = saved.json()["id"]

    listing = client.get("/api/projects")
    assert listing.status_code == 200
    assert listing.json()["projects"][0]["name"] == "Travel edit"

    loaded = client.get(f"/api/projects/{project_id}")
    assert loaded.status_code == 200
    assert loaded.json()["state"]["timeline_transition"] == "dissolve"

    deleted = client.delete(f"/api/projects/{project_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/projects/{project_id}").status_code == 404


def test_project_save_rejects_missing_clip_file(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PROJECTS", tmp_path)
    response = client.post("/api/projects", json={
        "name": "Broken project",
        "state": {"timeline_files": [{
            "filename": "missing.mp4", "duration": 5, "trimStart": 0, "trimEnd": 5
        }]}
    })
    assert response.status_code == 404


def test_project_name_must_not_be_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PROJECTS", tmp_path)
    response = client.post("/api/projects", json={"name": " ", "state": {}})
    assert response.status_code == 400


def test_transition_export_job_completes_and_returns_result(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "PROJECTS", tmp_path)
    monkeypatch.setattr(main, "export_timeline_transition", lambda payload, job_id=None: {
        "filename": "finished.mp4", "url": "/media/finished.mp4",
        "clips": len(payload["clips"]), "transition": payload["transition"],
        "transition_duration": payload["transition_duration"],
    })
    response = client.post("/api/export/jobs/timeline-transition", json={
        "clips": [{"filename": "a.mp4"}, {"filename": "b.mp4"}],
        "transition": "fade", "transition_duration": 0.5,
    })
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    status = client.get(f"/api/export/jobs/{job_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert status.json()["progress"] == 100
    assert status.json()["result"]["filename"] == "finished.mp4"


def test_export_job_rejects_invalid_job_id():
    response = client.get("/api/export/jobs/not-a-valid-id")
    assert response.status_code == 400


def test_export_job_returns_404_for_unknown_id():
    response = client.get("/api/export/jobs/" + "a" * 32)
    assert response.status_code == 404

 
def test_export_job_can_be_cancelled_before_worker_starts():
    job_id = "b" * 32
    main._export_jobs[job_id] = {
        "id": job_id, "status": "queued", "progress": 0,
        "message": "Export queued", "result": None,
    }
    response = client.post(f"/api/export/jobs/{job_id}/cancel")
    assert response.status_code == 200
    assert response.json()["cancel_requested"] is True
    assert main._export_jobs[job_id]["cancel_requested"] is True
    main._export_jobs.pop(job_id, None)


def test_completed_export_job_cannot_be_cancelled():
    job_id = "c" * 32
    main._export_jobs[job_id] = {
        "id": job_id, "status": "completed", "progress": 100,
        "message": "Export complete", "result": {"filename": "done.mp4"},
    }
    response = client.post(f"/api/export/jobs/{job_id}/cancel")
    assert response.status_code == 409
    main._export_jobs.pop(job_id, None)


def test_cancel_export_job_rejects_unknown_id():
    response = client.post("/api/export/jobs/" + "d" * 32 + "/cancel")
    assert response.status_code == 404


def test_export_history_survives_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PROJECTS", tmp_path)
    job_id = "e" * 32
    main._export_jobs[job_id] = {
        "id": job_id, "status": "completed", "progress": 100,
        "message": "Export complete", "result": {"filename": "saved.mp4"},
        "created_at": "2026-11-10T10:00:00+00:00", "finished_at": None,
    }
    main._persist_export_jobs()
    main._export_jobs.pop(job_id)
    main._load_export_jobs()
    assert main._export_jobs[job_id]["result"]["filename"] == "saved.mp4"
    main._export_jobs.pop(job_id, None)


def test_running_export_is_marked_interrupted_after_reload(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PROJECTS", tmp_path)
    job_id = "f" * 32
    main._export_jobs[job_id] = {
        "id": job_id, "status": "running", "progress": 5,
        "message": "Preparing video clips", "result": None,
        "created_at": "2026-11-10T10:00:00+00:00", "finished_at": None,
    }
    main._persist_export_jobs()
    main._export_jobs.pop(job_id)
    main._load_export_jobs()
    assert main._export_jobs[job_id]["status"] == "interrupted"
    assert "restarted" in main._export_jobs[job_id]["message"]
    main._export_jobs.pop(job_id, None)


def test_export_history_endpoint_returns_saved_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "PROJECTS", tmp_path)
    job_id = "9" * 32
    main._export_jobs[job_id] = {
        "id": job_id, "status": "completed", "progress": 100,
        "message": "Export complete", "result": {"filename": "history.mp4"},
        "created_at": "2026-11-10T10:00:00+00:00",
    }
    main._persist_export_jobs()
    response = client.get("/api/export/jobs")
    assert response.status_code == 200
    assert response.json()["total"] >= 1
    assert any(job["id"] == job_id for job in response.json()["jobs"])
    main._export_jobs.pop(job_id, None)



def test_ffmpeg_progress_percent_supports_both_time_formats():
    assert main._ffmpeg_progress_percent("out_time_ms=5000000", 10) == 50
    assert main._ffmpeg_progress_percent("out_time=00:00:07.500", 10) == 75


def test_ffmpeg_progress_percent_is_bounded_and_ignores_invalid_values():
    assert main._ffmpeg_progress_percent("out_time_ms=99999999", 10) == 99
    assert main._ffmpeg_progress_percent("out_time=N/A", 10) is None
    assert main._ffmpeg_progress_percent("progress=end", 10) is None
    assert main._ffmpeg_progress_percent("out_time_ms=1000000", 0) is None

from pathlib import Path
import json
import math
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "media"
MEDIA.mkdir(parents=True, exist_ok=True)
PROJECTS = ROOT / "projects"
PROJECTS.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="JARVIS AI Video Studio API", version="0.16.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=MEDIA), name="media")

ALLOWED = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
ALLOWED_AUDIO = {".mp3", ".wav", ".aac", ".m4a", ".ogg", ".flac"}
_whisper_model = None
_export_jobs = {}
_export_processes = {}


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _export_history_path():
    return PROJECTS / "export_jobs.json"


def _persist_export_jobs():
    PROJECTS.mkdir(parents=True, exist_ok=True)
    path = _export_history_path()
    temporary = path.with_suffix(".json.tmp")
    records = sorted(_export_jobs.values(), key=lambda item: item.get("created_at", ""), reverse=True)[:100]
    temporary.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_export_jobs():
    path = _export_history_path()
    if not path.is_file():
        return
    try:
        records = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            return
        for job in records[:100]:
            if not isinstance(job, dict) or not re.fullmatch(r"[a-f0-9]{32}", str(job.get("id", ""))):
                continue
            if job.get("status") in {"queued", "running"}:
                job.update({"status": "interrupted", "progress": 0, "message": "API restarted before this export finished", "cancel_requested": False})
                job["finished_at"] = _utc_now()
            _export_jobs[job["id"]] = job
        _persist_export_jobs()
    except (OSError, ValueError, TypeError):
        return


def _update_export_job(job_id, changes):
    job = _export_jobs[job_id]
    job.update(changes)
    if job.get("status") in {"completed", "failed", "cancelled", "interrupted"}:
        job.setdefault("finished_at", _utc_now())
    _persist_export_jobs()
    return job


_load_export_jobs()


def get_media_file(filename: str) -> Path:
    source = MEDIA / Path(str(filename)).name
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Video not found")
    return source


def run_ffprobe(source: Path) -> dict:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)],
            check=True, capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFprobe is not installed on the server")
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail=exc.stderr[-1000:] or "Could not read video metadata")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Video analysis timed out")
    return json.loads(result.stdout)


def srt_time(seconds: float) -> str:
    millis = max(0, round(float(seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "JARVIS AI Video Studio", "version": "0.16.0"}


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in ALLOWED:
        raise HTTPException(status_code=415, detail="Unsupported video format")
    name = f"{uuid.uuid4().hex}{suffix}"
    target = MEDIA / name
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"filename": name, "original_name": file.filename, "url": f"/media/{name}"}


@app.get("/api/video/{filename}/info")
def video_info(filename: str):
    source = get_media_file(filename)
    data = run_ffprobe(source)
    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})
    duration = float(data.get("format", {}).get("duration") or video_stream.get("duration") or 0)
    return {
        "filename": source.name,
        "duration": round(duration, 3),
        "width": video_stream.get("width"),
        "height": video_stream.get("height"),
        "video_codec": video_stream.get("codec_name"),
        "audio_codec": audio_stream.get("codec_name"),
        "has_audio": bool(audio_stream),
        "size_bytes": source.stat().st_size,
    }


@app.get("/api/video/{filename}/waveform")
def audio_waveform(filename: str, points: int = 240):
    """Return a compact audio amplitude envelope for timeline visualization."""
    source = get_media_file(filename)
    points = min(600, max(32, points))
    info = run_ffprobe(source)
    streams = info.get("streams", [])
    audio_stream = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not audio_stream:
        return {"filename": source.name, "has_audio": False, "duration": 0, "samples": []}
    duration = float(info.get("format", {}).get("duration") or audio_stream.get("duration") or 0)
    if duration <= 0:
        raise HTTPException(status_code=422, detail="Audio duration is unavailable")
    # Bound processing time and response size for long uploads.
    analysed_duration = min(duration, 300.0)
    command = [
        "ffmpeg", "-v", "error", "-i", str(source), "-t", str(analysed_duration),
        "-vn", "-ac", "1", "-ar", str(points * 20), "-f", "s16le", "pipe:1",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, timeout=180)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server")
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="replace")[-1000:]
        raise HTTPException(status_code=422, detail=detail or "Audio waveform extraction failed")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Audio waveform extraction timed out")
    import array
    samples = array.array("h")
    samples.frombytes(result.stdout[:len(result.stdout) - (len(result.stdout) % 2)])
    if not samples:
        return {"filename": source.name, "has_audio": True, "duration": analysed_duration, "samples": [0] * points}
    stride = max(1, len(samples) // points)
    peaks = []
    for index in range(points):
        chunk = samples[index * stride:(index + 1) * stride] if index < points - 1 else samples[index * stride:]
        peaks.append(round(max((abs(value) for value in chunk), default=0) / 32768, 3))
    return {
        "filename": source.name, "has_audio": True,
        "duration": round(analysed_duration, 3), "truncated": duration > analysed_duration,
        "samples": peaks,
    }


@app.post("/api/upload/audio")
async def upload_audio(file: UploadFile = File(...)):
    suffix = Path(file.filename or "music.mp3").suffix.lower()
    if suffix not in ALLOWED_AUDIO:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    name = f"{uuid.uuid4().hex}{suffix}"
    target = MEDIA / name
    with target.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    return {"filename": name, "original_name": file.filename, "url": f"/media/{name}"}


@app.post("/api/export/audio-mix")
def export_audio_mix(payload: dict):
    source = get_media_file(payload.get("filename", ""))
    music = get_media_file(payload.get("audio_filename", ""))
    if music.suffix.lower() not in ALLOWED_AUDIO:
        raise HTTPException(status_code=415, detail="Background track must be an audio file")
    try:
        music_volume = float(payload.get("music_volume", 0.25))
        original_volume = float(payload.get("original_volume", 1.0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Audio volume values must be numbers")
    if not 0 <= music_volume <= 2 or not 0 <= original_volume <= 2:
        raise HTTPException(status_code=400, detail="Audio volume must be between 0 and 2")
    info = run_ffprobe(source)
    streams = info.get("streams", [])
    if not any(item.get("codec_type") == "video" for item in streams):
        raise HTTPException(status_code=422, detail="Source file has no video stream")
    has_audio = any(item.get("codec_type") == "audio" for item in streams)
    output_name = f"{source.stem}-music-{uuid.uuid4().hex[:8]}.mp4"
    output = MEDIA / output_name
    command = ["ffmpeg", "-y", "-i", str(source), "-stream_loop", "-1", "-i", str(music)]
    if has_audio:
        filter_graph = (
            f"[0:a]volume={original_volume}[original];"
            f"[1:a]volume={music_volume}[music];"
            "[original][music]amix=inputs=2:duration=first:dropout_transition=2[mixed]"
        )
    else:
        filter_graph = f"[1:a]volume={music_volume}[mixed]"
    command += ["-filter_complex", filter_graph, "-map", "0:v:0", "-map", "[mixed]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-shortest", "-movflags", "+faststart", str(output)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server")
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail=exc.stderr[-1500:] or "Audio mixing failed")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Audio mixing timed out")
    return {"filename": output_name, "url": f"/media/{output_name}"}


@app.post("/api/video/{filename}/captions")
def generate_captions(filename: str, language: str = "auto"):
    """Generate an SRT subtitle file using the optional local Whisper model."""
    global _whisper_model
    source = get_media_file(filename)
    if language not in {"auto", "hi", "en"}:
        raise HTTPException(status_code=400, detail="Language must be auto, hi or en")
    try:
        import whisper
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Auto captions need the optional AI packages. Install backend/requirements-ai.txt first.",
        )
    audio_path = MEDIA / f"{uuid.uuid4().hex}.wav"
    subtitle_path = MEDIA / f"{source.stem}-captions-{uuid.uuid4().hex[:8]}.srt"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)],
            check=True, capture_output=True, text=True, timeout=600,
        )
        if _whisper_model is None:
            _whisper_model = whisper.load_model("base")
        result = _whisper_model.transcribe(
            str(audio_path), language=None if language == "auto" else language,
            task="transcribe", fp16=False,
        )
        segments = result.get("segments", [])
        if not segments:
            raise HTTPException(status_code=422, detail="No speech was detected in this video")
        blocks = []
        for index, segment in enumerate(segments, 1):
            text = str(segment.get("text", "")).strip()
            if text:
                blocks.append(
                    f"{index}\n{srt_time(segment['start'])} --> {srt_time(segment['end'])}\n{text}"
                )
        subtitle_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
        return {
            "filename": subtitle_path.name,
            "url": f"/media/{subtitle_path.name}",
            "language": result.get("language", language),
            "segments": len(blocks),
        }
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server")
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail=exc.stderr[-1200:] or "Audio extraction failed")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Audio extraction timed out")
    finally:
        audio_path.unlink(missing_ok=True)



@app.post("/api/export/captions")
def burn_captions(payload: dict):
    """Burn a generated SRT file into a video and return a new MP4."""
    source = get_media_file(payload.get("filename", ""))
    subtitle_name = Path(str(payload.get("subtitle_filename", ""))).name
    if not subtitle_name.endswith(".srt"):
        raise HTTPException(status_code=400, detail="A generated .srt subtitle file is required")
    subtitle = MEDIA / subtitle_name
    if not subtitle.is_file():
        raise HTTPException(status_code=404, detail="Subtitle file not found; generate captions again")
    # Escape characters significant to FFmpeg's filter parser.
    subtitle_path = str(subtitle.resolve()).replace("\\\\", "\\\\\\\\").replace(":", "\\\\:").replace("'", "\\\\'")
    output_name = f"{source.stem}-subtitled-{uuid.uuid4().hex[:8]}.mp4"
    output = MEDIA / output_name
    command = [
        "ffmpeg", "-y", "-i", str(source), "-vf", f"subtitles='{subtitle_path}'",
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
        "-movflags", "+faststart", str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server")
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail=exc.stderr[-1500:] or "Subtitle burn-in failed")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Subtitle export timed out")
    return {"filename": output_name, "url": f"/media/{output_name}"}




@app.post("/api/export/text")
def export_text_overlay(payload: dict):
    """Render a user-supplied text overlay into a new MP4."""
    source = get_media_file(payload.get("filename", ""))
    overlay_text = str(payload.get("text", "")).strip()
    if not overlay_text:
        raise HTTPException(status_code=400, detail="Overlay text cannot be empty")
    if len(overlay_text) > 300:
        raise HTTPException(status_code=400, detail="Overlay text must be 300 characters or fewer")
    try:
        font_size = int(payload.get("font_size", 42))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Font size must be a whole number")
    if not 16 <= font_size <= 96:
        raise HTTPException(status_code=400, detail="Font size must be between 16 and 96")
    positions = {
        "top": "(w-text_w)/2:40",
        "center": "(w-text_w)/2:(h-text_h)/2",
        "bottom": "(w-text_w)/2:h-text_h-40",
        "top-left": "40:40",
        "top-right": "w-text_w-40:40",
        "bottom-left": "40:h-text_h-40",
        "bottom-right": "w-text_w-40:h-text_h-40",
    }
    position = str(payload.get("position", "bottom"))
    if position not in positions:
        raise HTTPException(status_code=400, detail="Unsupported text position")
    info = run_ffprobe(source)
    if not any(item.get("codec_type") == "video" for item in info.get("streams", [])):
        raise HTTPException(status_code=422, detail="Source file has no video stream")
    job = uuid.uuid4().hex[:8]
    text_file = MEDIA / f"overlay-{job}.txt"
    output_name = f"{source.stem}-text-{job}.mp4"
    output = MEDIA / output_name
    text_file.write_text(overlay_text, encoding="utf-8")
    def escape_filter_path(path: Path) -> str:
        return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    font_file = Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf")
    drawtext = (
        f"drawtext=fontfile='{escape_filter_path(font_file)}':"
        f"textfile='{escape_filter_path(text_file)}':fontcolor=white:fontsize={font_size}:expansion=none:"
        f"x={positions[position].split(':', 1)[0]}:y={positions[position].split(':', 1)[1]}:"
        "box=1:boxcolor=black@0.55:boxborderw=12"
    )
    command = [
        "ffmpeg", "-y", "-i", str(source), "-vf", drawtext,
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
        "-movflags", "+faststart", str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server")
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail=exc.stderr[-1500:] or "Text overlay export failed")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Text overlay export timed out")
    finally:
        text_file.unlink(missing_ok=True)
    return {"filename": output_name, "url": f"/media/{output_name}"}




@app.post("/api/export/fade")
def export_fade(payload: dict):
    """Apply fade-in and/or fade-out effects to a video and its audio."""
    source = get_media_file(payload.get("filename", ""))
    try:
        fade_in = float(payload.get("fade_in", 0))
        fade_out = float(payload.get("fade_out", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Fade durations must be numbers")
    if not all(map(lambda value: value >= 0, (fade_in, fade_out))):
        raise HTTPException(status_code=400, detail="Fade durations cannot be negative")
    info = run_ffprobe(source)
    streams = info.get("streams", [])
    video_stream = next((item for item in streams if item.get("codec_type") == "video"), None)
    if not video_stream:
        raise HTTPException(status_code=422, detail="Source file has no video stream")
    duration = float(info.get("format", {}).get("duration") or video_stream.get("duration") or 0)
    if duration <= 0:
        raise HTTPException(status_code=422, detail="Video duration is unavailable")
    if fade_in > duration or fade_out > duration or fade_in + fade_out > duration:
        raise HTTPException(status_code=400, detail="Combined fade durations cannot exceed video duration")
    if fade_in == 0 and fade_out == 0:
        raise HTTPException(status_code=400, detail="Set fade-in or fade-out duration")
    has_audio = any(item.get("codec_type") == "audio" for item in streams)
    filters = []
    video_filters = []
    if fade_in:
        video_filters.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out:
        video_filters.append(f"fade=t=out:st={max(0, duration - fade_out)}:d={fade_out}")
    if video_filters:
        filters.append(f"[0:v:0]{','.join(video_filters)}[v]")
    if has_audio:
        audio_filters = []
        if fade_in:
            audio_filters.append(f"afade=t=in:st=0:d={fade_in}")
        if fade_out:
            audio_filters.append(f"afade=t=out:st={max(0, duration - fade_out)}:d={fade_out}")
        filters.append(f"[0:a:0]{','.join(audio_filters)}[a]")
    output_name = f"{source.stem}-fade-{uuid.uuid4().hex[:8]}.mp4"
    output = MEDIA / output_name
    command = ["ffmpeg", "-y", "-i", str(source), "-filter_complex", ";".join(filters)]
    command += ["-map", "[v]"]
    if has_audio:
        command += ["-map", "[a]"]
    command += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    if has_audio:
        command += ["-c:a", "aac", "-b:a", "192k"]
    command += ["-movflags", "+faststart", str(output)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server")
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail=exc.stderr[-1500:] or "Fade export failed")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Fade export timed out")
    return {"filename": output_name, "url": f"/media/{output_name}"}


@app.post("/api/export/timeline")
def export_timeline(payload: dict):
    """Normalize clips to a common format, then join them in timeline order."""
    clips = payload.get("clips")
    if clips is None:
        names = payload.get("filenames", [])
        clips = [{"filename": name, "start": 0, "end": None} for name in names]
    if not isinstance(clips, list) or not 2 <= len(clips) <= 20:
        raise HTTPException(status_code=400, detail="Timeline needs between 2 and 20 clips")
    prepared = []
    for clip in clips:
        if not isinstance(clip, dict):
            raise HTTPException(status_code=400, detail="Each timeline clip must include filename, start and end")
        source = get_media_file(clip.get("filename", ""))
        try:
            start = float(clip.get("start", 0))
            end = clip.get("end")
            end = float(end) if end is not None else None
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid clip trim values")
        info = run_ffprobe(source)
        total = float(info.get("format", {}).get("duration") or 0)
        if start < 0 or (end is not None and (end <= start or (total and end > total + 0.05))):
            raise HTTPException(status_code=400, detail=f"Invalid trim range for {source.name}")
        if total and start >= total:
            raise HTTPException(status_code=400, detail=f"Trim start exceeds duration for {source.name}")
        clip_duration = (end - start) if end is not None else (total - start if total else None)
        if clip_duration is not None and clip_duration <= 0:
            raise HTTPException(status_code=400, detail=f"Clip duration is empty for {source.name}")
        prepared.append((source, start, clip_duration))
    job = uuid.uuid4().hex[:10]
    normalized = []
    concat_list = MEDIA / f"timeline-{job}.txt"
    output_name = f"jarvis-timeline-{job}.mp4"
    output = MEDIA / output_name
    try:
        for index, (source, trim_start, trim_duration) in enumerate(prepared):
            info = run_ffprobe(source)
            streams = info.get("streams", [])
            if not any(item.get("codec_type") == "video" for item in streams):
                raise HTTPException(status_code=422, detail=f"{source.name} has no video stream")
            has_audio = any(item.get("codec_type") == "audio" for item in streams)
            normalized_file = MEDIA / f"timeline-{job}-{index}.mp4"
            command = ["ffmpeg", "-y", "-ss", str(trim_start), "-i", str(source)]
            if trim_duration is not None:
                command += ["-t", str(trim_duration)]
            if not has_audio:
                command += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
            command += [
                "-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-shortest",
                "-movflags", "+faststart", str(normalized_file),
            ]
            subprocess.run(command, check=True, capture_output=True, text=True, timeout=1800)
            normalized.append(normalized_file)
        concat_list.write_text(
            "".join(f"file '{path.name}'\n" for path in normalized), encoding="utf-8"
        )
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
             "-c", "copy", "-movflags", "+faststart", str(output)],
            check=True, capture_output=True, text=True, timeout=1800,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server")
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail=exc.stderr[-1500:] or "Timeline export failed")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Timeline export timed out")
    finally:
        concat_list.unlink(missing_ok=True)
        for path in normalized:
            path.unlink(missing_ok=True)
    return {"filename": output_name, "url": f"/media/{output_name}", "clips": len(prepared)}


def _run_export_process(command, job_id=None, timeout=1800):
    """Run an FFmpeg step that can be stopped by its owning export job."""
    if not job_id:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if job_id:
        _export_processes[job_id] = process
    try:
        import time
        deadline = time.monotonic() + timeout
        while True:
            if job_id and _export_jobs.get(job_id, {}).get("cancel_requested"):
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                raise InterruptedError("Export cancelled by user")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                stdout, stderr = process.communicate()
                raise subprocess.TimeoutExpired(command, timeout, output=stdout, stderr=stderr)
            try:
                stdout, stderr = process.communicate(timeout=min(0.25, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        if job_id:
            _export_processes.pop(job_id, None)


@app.post("/api/export/timeline-transition")
def export_timeline_transition(payload: dict, job_id: str | None = None):
    """Join timeline clips with a video transition and matching audio crossfades."""
    clips = payload.get("clips")
    if not isinstance(clips, list) or not 2 <= len(clips) <= 20:
        raise HTTPException(status_code=400, detail="Transition export needs between 2 and 20 clips")
    transition = str(payload.get("transition", "fade"))
    allowed_transitions = {"fade", "dissolve", "wipeleft", "wiperight", "slideleft", "slideright", "circleopen"}
    if transition not in allowed_transitions:
        raise HTTPException(status_code=400, detail="Unsupported transition type")
    try:
        transition_duration = float(payload.get("transition_duration", 0.75))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Transition duration must be a number")
    if not math.isfinite(transition_duration) or not 0.1 <= transition_duration <= 3:
        raise HTTPException(status_code=400, detail="Transition duration must be between 0.1 and 3 seconds")

    prepared = []
    for clip in clips:
        if not isinstance(clip, dict):
            raise HTTPException(status_code=400, detail="Each clip must include filename, start and end")
        source = get_media_file(clip.get("filename", ""))
        try:
            start = float(clip.get("start", 0))
            end = float(clip.get("end"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid clip trim values")
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise HTTPException(status_code=400, detail="Invalid clip trim range")
        info = run_ffprobe(source)
        streams = info.get("streams", [])
        video_stream = next((item for item in streams if item.get("codec_type") == "video"), None)
        total = float(info.get("format", {}).get("duration") or (video_stream or {}).get("duration") or 0)
        if not video_stream:
            raise HTTPException(status_code=422, detail=f"{source.name} has no video stream")
        if total <= 0 or end > total + 0.05:
            raise HTTPException(status_code=400, detail=f"Trim range exceeds video duration for {source.name}")
        clip_duration = end - start
        if clip_duration <= transition_duration:
            raise HTTPException(status_code=400, detail="Each selected clip must be longer than the transition")
        prepared.append((source, start, clip_duration, any(item.get("codec_type") == "audio" for item in streams)))

    job = uuid.uuid4().hex[:10]
    normalized = []
    output_name = f"jarvis-transition-{job}.mp4"
    output = MEDIA / output_name
    try:
        for index, (source, trim_start, trim_duration, has_audio) in enumerate(prepared):
            normalized_file = MEDIA / f"transition-{job}-{index}.mp4"
            command = ["ffmpeg", "-y", "-ss", str(trim_start), "-i", str(source), "-t", str(trim_duration)]
            if not has_audio:
                command += ["-f", "lavfi", "-t", str(trim_duration), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
            command += [
                "-map", "0:v:0", "-map", "0:a:0" if has_audio else "1:a:0",
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-ar", "44100", "-ac", "2", "-t", str(trim_duration),
                "-movflags", "+faststart", str(normalized_file),
            ]
            _run_export_process(command, job_id=job_id, timeout=1800)
            normalized.append(normalized_file)

        graph = []
        video_label = "[0:v]"
        audio_label = "[0:a]"
        elapsed = prepared[0][2]
        for index in range(1, len(prepared)):
            next_video = f"[v{index}]"
            next_audio = f"[a{index}]"
            offset = elapsed - transition_duration
            graph.append(
                f"{video_label}[{index}:v]xfade=transition={transition}:duration={transition_duration}:offset={offset}{next_video}"
            )
            graph.append(
                f"{audio_label}[{index}:a]acrossfade=d={transition_duration}:c1=tri:c2=tri{next_audio}"
            )
            video_label, audio_label = next_video, next_audio
            elapsed += prepared[index][2] - transition_duration

        command = ["ffmpeg", "-y"]
        for path in normalized:
            command += ["-i", str(path)]
        command += [
            "-filter_complex", ";".join(graph),
            "-map", video_label, "-map", audio_label,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
        ]
        _run_export_process(command, job_id=job_id, timeout=3600)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server")
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail=exc.stderr[-1500:] or "Transition export failed")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Transition export timed out")
    finally:
        for path in normalized:
            path.unlink(missing_ok=True)
    return {
        "filename": output_name, "url": f"/media/{output_name}",
        "clips": len(prepared), "transition": transition,
        "transition_duration": transition_duration,
    }


@app.post("/api/export/trim")
def trim_video(payload: dict):
    source = get_media_file(payload.get("filename", ""))
    try:
        start = max(0.0, float(payload.get("start", 0)))
        duration = float(payload.get("duration", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid trim values")
    if duration <= 0 or duration > 3600:
        raise HTTPException(status_code=400, detail="Duration must be between 0 and 3600 seconds")
    info = run_ffprobe(source)
    total = float(info.get("format", {}).get("duration") or 0)
    if total and (start >= total or start + duration > total + 0.05):
        raise HTTPException(status_code=400, detail=f"Trim range exceeds video length ({total:.2f} seconds)")
    output_name = f"{source.stem}-edited-{uuid.uuid4().hex[:8]}.mp4"
    output = MEDIA / output_name
    command = [
        "ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration),
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
        "-movflags", "+faststart", str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server")
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail=exc.stderr[-1500:] or "FFmpeg export failed")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Export timed out")
    return {"filename": output_name, "url": f"/media/{output_name}"}


def project_path(project_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", str(project_id)):
        raise HTTPException(status_code=400, detail="Invalid project ID")
    return PROJECTS / f"{project_id}.json"


@app.get("/api/projects")
def list_projects():
    projects = []
    for path in PROJECTS.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            projects.append({
                "id": path.stem,
                "name": data.get("name", "Untitled project"),
                "updated_at": data.get("updated_at"),
            })
        except (OSError, ValueError):
            continue
    projects.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return {"projects": projects}


@app.post("/api/projects")
def save_project(payload: dict):
    name = str(payload.get("name", "Untitled project")).strip()
    if not name or len(name) > 80:
        raise HTTPException(status_code=400, detail="Project name must be 1–80 characters")
    state = payload.get("state")
    if not isinstance(state, dict):
        raise HTTPException(status_code=400, detail="Project state must be an object")
    clips = state.get("timeline_files", [])
    if not isinstance(clips, list) or len(clips) > 20:
        raise HTTPException(status_code=400, detail="Project can contain up to 20 timeline clips")
    safe_clips = []
    for clip in clips:
        if not isinstance(clip, dict):
            raise HTTPException(status_code=400, detail="Invalid timeline clip")
        source = get_media_file(clip.get("filename", ""))
        try:
            duration = float(clip.get("duration", 0))
            trim_start = float(clip.get("trimStart", 0))
            trim_end = float(clip.get("trimEnd", duration))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid saved clip timing")
        if duration <= 0 or trim_start < 0 or trim_end <= trim_start or trim_end > duration + 0.05:
            raise HTTPException(status_code=400, detail="Saved clip trim range is invalid")
        safe_clips.append({
            "filename": source.name,
            "url": f"/media/{source.name}",
            "original_name": str(clip.get("original_name", source.name))[:255],
            "duration": duration, "trimStart": trim_start, "trimEnd": trim_end,
        })
    project_id = str(payload.get("id") or uuid.uuid4().hex)
    target = project_path(project_id)
    from datetime import datetime, timezone
    existing = {}
    if target.is_file():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = {}
    document = {
        "id": project_id, "name": name, "state": {**state, "timeline_files": safe_clips},
        "created_at": existing.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": project_id, "name": name, "updated_at": document["updated_at"]}


@app.get("/api/projects/{project_id}")
def load_project(project_id: str):
    target = project_path(project_id)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise HTTPException(status_code=500, detail="Saved project is unreadable")
    return document


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str):
    target = project_path(project_id)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Project not found")
    target.unlink()
    return {"deleted": True, "id": project_id}


def _run_export_job(job_id: str, payload: dict):
    _update_export_job(job_id, {"status": "running", "progress": 5, "message": "Preparing video clips"})
    try:
        if _export_jobs[job_id].get("cancel_requested"):
            _update_export_job(job_id, {"status": "cancelled", "progress": 0, "message": "Export cancelled"})
            return
        result = export_timeline_transition(payload, job_id=job_id)
        if _export_jobs[job_id].get("cancel_requested"):
            _update_export_job(job_id, {"status": "cancelled", "progress": 0, "message": "Export cancelled"})
        else:
            _update_export_job(job_id, {
                "status": "completed", "progress": 100,
                "message": "Export complete", "result": result,
            })
    except InterruptedError:
        _update_export_job(job_id, {"status": "cancelled", "progress": 0, "message": "Export cancelled"})
    except HTTPException as exc:
        _update_export_job(job_id, {"status": "failed", "progress": 0, "message": str(exc.detail)})
    except Exception:
        _update_export_job(job_id, {"status": "failed", "progress": 0, "message": "Unexpected export error"})


@app.post("/api/export/jobs/timeline-transition", status_code=202)
def start_transition_export_job(payload: dict, background_tasks: BackgroundTasks):
    job_id = uuid.uuid4().hex
    _export_jobs[job_id] = {
        "id": job_id, "status": "queued", "progress": 0,
        "message": "Export queued", "result": None,
        "created_at": _utc_now(), "finished_at": None,
        "cancel_requested": False,
    }
    _persist_export_jobs()
    background_tasks.add_task(_run_export_job, job_id, payload)
    return {"job_id": job_id, "status": "queued", "status_url": f"/api/export/jobs/{job_id}"}


@app.post("/api/export/jobs/{job_id}/cancel")
def cancel_export_job(job_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Invalid export job ID")
    job = _export_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    if job["status"] in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=409, detail="Cannot cancel a finished export")
    _update_export_job(job_id, {"cancel_requested": True, "message": "Cancellation requested"})
    return {"id": job_id, "status": job["status"], "cancel_requested": True}


@app.get("/api/export/jobs")
def list_export_jobs(limit: int = 50):
    limit = min(100, max(1, limit))
    jobs = sorted(_export_jobs.values(), key=lambda item: item.get("created_at", ""), reverse=True)
    return {"jobs": jobs[:limit], "total": len(jobs)}


@app.get("/api/export/jobs/{job_id}")
def get_export_job(job_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise HTTPException(status_code=400, detail="Invalid export job ID")
    job = _export_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Export job not found")
    return job

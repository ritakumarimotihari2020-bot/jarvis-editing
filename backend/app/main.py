from pathlib import Path
import json
import shutil
import subprocess
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "media"
MEDIA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="JARVIS AI Video Studio API", version="0.10.0")
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
    return {"status": "ok", "service": "JARVIS AI Video Studio", "version": "0.10.0"}


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

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

app = FastAPI(title="JARVIS AI Video Studio API", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=MEDIA), name="media")

ALLOWED = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
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
    return {"status": "ok", "service": "JARVIS AI Video Studio", "version": "0.4.0"}


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

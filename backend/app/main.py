from pathlib import Path
import shutil
import subprocess
import uuid

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "media"
MEDIA.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="JARVIS AI Video Studio API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/media", StaticFiles(directory=MEDIA), name="media")

ALLOWED = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "JARVIS AI Video Studio", "version": "0.1.0"}

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

@app.post("/api/export/trim")
def trim_video(payload: dict):
    source = MEDIA / Path(str(payload.get("filename", ""))).name
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Video not found")
    try:
        start = max(0.0, float(payload.get("start", 0)))
        duration = float(payload.get("duration", 0))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid trim values")
    if duration <= 0 or duration > 3600:
        raise HTTPException(status_code=400, detail="Duration must be between 0 and 3600 seconds")
    output_name = f"{source.stem}-edited-{uuid.uuid4().hex[:8]}.mp4"
    output = MEDIA / output_name
    command = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source), "-t", str(duration), "-c:v", "libx264", "-c:a", "aac", "-movflags", "+faststart", str(output)]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=1800)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="FFmpeg is not installed on the server")
    except subprocess.CalledProcessError as exc:
        raise HTTPException(status_code=422, detail=exc.stderr[-1500:] or "FFmpeg export failed")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Export timed out")
    return {"filename": output_name, "url": f"/media/{output_name}"}

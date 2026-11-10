# JARVIS AI Video Studio — roadmap

## Implemented in 0.2.0
- Responsive React/Vite editor interface
- FastAPI health and upload endpoints
- FFprobe metadata inspection (duration, dimensions, codecs, audio presence, file size)
- FFmpeg trim/export with trim-range validation
- Docker image with FFmpeg/FFprobe installed

## Next milestones
1. Add a visual multi-clip timeline with draggable trim handles.
2. Add text overlays, subtitle tracks, transitions, and audio mixing.
3. Add speech-to-text captions (Whisper) and Hindi/English command parsing.
4. Add project persistence and background export jobs.
5. Package the mobile-friendly client as an Android app (Capacitor) after the web workflow is stable.

## Current limitations
This is an early editor scaffold, not a full AI editor. AI scene detection, auto-captions, multi-track editing, authentication, and Android APK packaging are not implemented yet. The API needs FFmpeg and FFprobe on the server.

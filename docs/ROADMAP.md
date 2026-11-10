# JARVIS AI Video Studio — roadmap

## Implemented in 0.4.0
- Responsive React/Vite editor interface
- FastAPI upload, health, and FFprobe metadata endpoints
- FFmpeg trim/export with trim-range validation
- Browser speech recognition controls for Hindi/English trim and export commands
- Optional Whisper-powered Hindi/English/auto speech-to-text captions as downloadable SRT
- SRT caption text preview in the editor
- FFmpeg subtitle burn-in export to a new MP4 file
- Docker image with FFmpeg/FFprobe installed

## Enable AI auto-captions
Install the base backend requirements, then install `backend/requirements-ai.txt`.
The first caption request downloads Whisper's `base` model, so the server needs internet access and enough RAM/disk. CPU transcription can be slow. Voice commands use browser Web Speech API and require a supported browser (Chrome on Android is recommended) and microphone permission.

## Next milestones
1. Add a visual multi-clip timeline with draggable trim handles.
2. Add text overlays, transitions, and audio mixing.
3. Add project persistence and background export jobs.
4. Add automated backend/frontend tests and deployment configuration.
5. Package the mobile-friendly client as an Android app (Capacitor) after the web workflow is stable.

## Current limitations
This is an early editor scaffold, not a full AI editor. Voice recognition depends on browser support. Whisper captions are optional and are not ready until the AI requirements and model are installed on the server. Subtitle burn-in requires FFmpeg with the subtitles/libass filter available. APK packaging, authentication, and cloud deployment are not implemented yet. The API needs FFmpeg and FFprobe on the server.

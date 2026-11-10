import React, { useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const playerRef = useRef(null);
  const [file, setFile] = useState(null);
  const [video, setVideo] = useState(null);
  const [info, setInfo] = useState(null);
  const [start, setStart] = useState('0');
  const [duration, setDuration] = useState('10');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('Choose a video to begin editing.');
  const [listening, setListening] = useState(false);
  const [commandText, setCommandText] = useState('');
  const [caption, setCaption] = useState(null);
  const [captionLanguage, setCaptionLanguage] = useState('auto');
  const [captionPreview, setCaptionPreview] = useState('');
  const [waveform, setWaveform] = useState(null);
  const [musicFile, setMusicFile] = useState(null);
  const [musicVolume, setMusicVolume] = useState(25);
  const [originalVolume, setOriginalVolume] = useState(100);
  const [overlayText, setOverlayText] = useState('');
  const [overlayPosition, setOverlayPosition] = useState('bottom');
  const [overlayFontSize, setOverlayFontSize] = useState(42);
  const [fadeIn, setFadeIn] = useState(1);
  const [fadeOut, setFadeOut] = useState(1);
  const [timelineFiles, setTimelineFiles] = useState([]);
  const [timelinePreviewing, setTimelinePreviewing] = useState(false);
  const [timelinePreviewIndex, setTimelinePreviewIndex] = useState(0);


  async function loadWaveform(filename) {
    setWaveform(null);
    try {
      const res = await fetch(`${API}/api/video/${encodeURIComponent(filename)}/waveform?points=240`);
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Waveform unavailable');
      setWaveform(body);
    } catch (err) {
      setWaveform({ has_audio: false, samples: [], error: err.message });
    }
  }

  async function addTimelineFiles(files) {
    const selected = Array.from(files || []).filter(item => item.type.startsWith('video/'));
    if (!selected.length) return;
    if (timelineFiles.length + selected.length > 20) {
      setMessage('Timeline mein maximum 20 clips add kar sakte hain.');
      return;
    }
    setBusy(true); setMessage('Timeline clips upload ho rahe hain…');
    try {
      const added = [];
      for (const item of selected) {
        const data = new FormData(); data.append('file', item);
        const res = await fetch(API + '/api/upload', { method: 'POST', body: data });
        const body = await res.json();
        if (!res.ok) throw new Error(body.detail || ('Upload failed: ' + item.name));
        const metaRes = await fetch(API + '/api/video/' + encodeURIComponent(body.filename) + '/info');
        const meta = await metaRes.json();
        if (!metaRes.ok) throw new Error(meta.detail || 'Could not analyse ' + item.name);
        added.push({ ...body, duration: meta.duration, trimStart: 0, trimEnd: meta.duration });
      }
      setTimelineFiles(current => [...current, ...added]);
      setVideo(current => current || added[0]);
      setMessage(added.length + ' clip(s) timeline mein add ho gaye.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  function startTimelinePreview() {
    if (!timelineFiles.length) return;
    setTimelinePreviewIndex(0);
    setTimelinePreviewing(true);
    setMessage('Timeline preview chal raha hai…');
  }

  function advanceTimelinePreview() {
    setTimelinePreviewIndex(current => {
      if (current + 1 >= timelineFiles.length) {
        setTimelinePreviewing(false);
        setMessage('Timeline preview complete.');
        return current;
      }
      return current + 1;
    });
  }

  function handleTimelinePreviewLoaded() {
    if (!timelinePreviewing) return;
    const clip = timelineFiles[timelinePreviewIndex];
    if (!clip || !playerRef.current) return;
    playerRef.current.currentTime = Number(clip.trimStart) || 0;
    playerRef.current.play().catch(() => setMessage('Preview ready. Player par Play dabayein.'));
  }

  function handleTimelinePreviewTime() {
    if (!timelinePreviewing) return;
    const clip = timelineFiles[timelinePreviewIndex];
    if (clip && playerRef.current && playerRef.current.currentTime >= Number(clip.trimEnd) - 0.04) {
      if (timelinePreviewIndex + 1 < timelineFiles.length) advanceTimelinePreview();
      else {
        playerRef.current.pause();
        setTimelinePreviewing(false);
        setMessage('Timeline preview complete.');
      }
    }
  }

  function moveTimelineClip(index, direction) {
    setTimelineFiles(current => {
      const next = [...current], target = index + direction;
      if (target < 0 || target >= next.length) return current;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function exportTimeline() {
    if (timelineFiles.length < 2) {
      setMessage('Timeline export ke liye kam se kam 2 clips add karein.');
      return;
    }
    const invalid = timelineFiles.find(item => !Number.isFinite(Number(item.trimStart)) || !Number.isFinite(Number(item.trimEnd)) || Number(item.trimStart) < 0 || Number(item.trimEnd) <= Number(item.trimStart) || Number(item.trimEnd) > Number(item.duration) + 0.05);
    if (invalid) { setMessage('Har clip ka Start aur End uski duration ke andar rakhein.'); return; }
    setBusy(true); setMessage('Timeline render ho rahi hai. Multiple clips mein time lag sakta hai…');
    try {
      const res = await fetch(API + '/api/export/timeline', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ clips: timelineFiles.map(item => ({ filename: item.filename, start: Number(item.trimStart), end: Number(item.trimEnd) })) })
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Timeline export failed');
      setVideo({ ...body, original_name: 'JARVIS Timeline Export' });
      setInfo(null); setCaption(null); setCaptionPreview('');
      setMessage(body.clips + ' clips successfully joined. Player menu se video save karein.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  async function upload() {
    if (!file) return;
    setBusy(true); setMessage('Uploading and analysing video…');
    try {
      const data = new FormData(); data.append('file', file);
      const res = await fetch(`${API}/api/upload`, { method: 'POST', body: data });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Upload failed');
      setVideo(body);
      const metaRes = await fetch(`${API}/api/video/${encodeURIComponent(body.filename)}/info`);
      const meta = await metaRes.json();
      if (!metaRes.ok) throw new Error(meta.detail || 'Video analysis failed');
      setInfo(meta);
      await loadWaveform(body.filename);
      setDuration(String(Math.max(0.1, Math.floor(meta.duration * 10) / 10)));
      setCaption(null);
      setMessage('Video analysed. Try a voice command or generate captions.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  async function exportTrim() {
    if (!video) return;
    const trimStart = Number(start), trimDuration = Number(duration);
    if (!Number.isFinite(trimStart) || !Number.isFinite(trimDuration) || trimStart < 0 || trimDuration <= 0 || (info?.duration && trimStart + trimDuration > info.duration + 0.05)) {
      setMessage('Trim range invalid hai. Start aur duration video ki length ke andar rakhein.');
      return;
    }
    setBusy(true); setMessage('Rendering your edit…');
    try {
      const res = await fetch(`${API}/api/export/trim`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: video.filename, start: trimStart, duration: trimDuration })
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Export failed');
      setVideo({ ...body, original_name: 'Edited export' });
      setInfo(null); setCaption(null);
      setMessage('Your edited video is ready. Use the video player menu to save it.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  function setTrimStartToPlayhead() {
    const current = playerRef.current?.currentTime;
    if (!Number.isFinite(current)) return;
    setStart(current.toFixed(1));
    setMessage(`Trim start set to ${current.toFixed(1)} seconds.`);
  }

  function setTrimEndToPlayhead() {
    const current = playerRef.current?.currentTime;
    if (!Number.isFinite(current)) return;
    const nextDuration = current - Number(start || 0);
    if (nextDuration <= 0) {
      setMessage('End point, start point ke baad hona chahiye.');
      return;
    }
    setDuration(nextDuration.toFixed(1));
    setMessage(`Trim duration set to ${nextDuration.toFixed(1)} seconds.`);
  }

  function runVoiceCommand(raw) {
    const text = raw.toLowerCase().trim();
    setCommandText(raw);
    const startMatch = text.match(/(?:start|शुरू|आरंभ|स्टार्ट)\s*(?:time|समय)?\s*(?:को)?\s*(\d+(?:\.\d+)?)/);
    const durationMatch = text.match(/(?:duration|लंबाई|अवधि|कितने सेकंड)\s*(?:को)?\s*(\d+(?:\.\d+)?)/);
    if (startMatch) setStart(startMatch[1]);
    if (durationMatch) setDuration(durationMatch[1]);
    if (/upload|अपलोड/.test(text)) {
      document.querySelector('input[type="file"]')?.click();
      setMessage('Choose a video file, then tap Upload & Analyse.');
    } else if (/export|save|निर्यात|एक्सपोर्ट|सेव/.test(text)) {
      setMessage('Voice command received: exporting your current trim.');
      exportTrim();
    } else if (startMatch || durationMatch) {
      setMessage('Voice command applied. Check the trim values, then say Export or tap Export Video.');
    } else {
      setMessage('Command not recognised. Try: start time 5, duration 20, or export video.');
    }
  }

  function startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setMessage('Voice recognition is not supported in this browser. Try Chrome on Android.');
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = 'hi-IN';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = event => runVoiceCommand(event.results[0][0].transcript);
    recognition.onerror = event => setMessage(`Voice error: ${event.error}`);
    recognition.onend = () => setListening(false);
    recognition.start();
    setListening(true);
    setMessage('सुन रहा हूँ… हिंदी या English command बोलें।');
  }

  async function generateCaptions() {
    if (!video) return;
    setBusy(true); setCaption(null); setMessage('Whisper AI speech recognition is processing your video…');
    try {
      const res = await fetch(`${API}/api/video/${encodeURIComponent(video.filename)}/captions?language=${captionLanguage}`, { method: 'POST' });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Caption generation failed');
      setCaption(body);
      const srtRes = await fetch(`${API}${body.url}`);
      setCaptionPreview(srtRes.ok ? await srtRes.text() : 'Preview unavailable.');
      setMessage(`Captions ready: ${body.segments} subtitle segments detected.`);
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }






  async function exportFade() {
    if (!video) return;
    if (info?.duration && fadeIn + fadeOut > info.duration) {
      setMessage('Fade in aur fade out ka total video duration se zyada nahi ho sakta.');
      return;
    }
    setBusy(true); setMessage('Video aur audio par fade effects render ho rahe hain…');
    try {
      const res = await fetch(`${API}/api/export/fade`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: video.filename, fade_in: fadeIn, fade_out: fadeOut
        })
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Fade export failed');
      setVideo({ ...body, original_name: 'Fade effects export' });
      setInfo(null); setCaption(null); setCaptionPreview('');
      setMessage('Fade in/out effects video aur audio par apply ho gaye. Player menu se MP4 save karein.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  async function exportTextOverlay() {
    if (!video || !overlayText.trim()) return;
    setBusy(true); setMessage('Video par text overlay render ho raha hai…');
    try {
      const res = await fetch(`${API}/api/export/text`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: video.filename, text: overlayText,
          position: overlayPosition, font_size: overlayFontSize
        })
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Text overlay export failed');
      setVideo({ ...body, original_name: 'Text overlay export' });
      setInfo(null); setCaption(null); setCaptionPreview('');
      setMessage('Text video mein add ho gaya. Player menu se MP4 save karein.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  async function exportAudioMix() {
    if (!video || !musicFile) return;
    setBusy(true); setMessage('Background music mix ho raha hai…');
    try {
      const uploadData = new FormData();
      uploadData.append('file', musicFile);
      const uploadRes = await fetch(`${API}/api/upload/audio`, { method: 'POST', body: uploadData });
      const audio = await uploadRes.json();
      if (!uploadRes.ok) throw new Error(audio.detail || 'Music upload failed');
      const res = await fetch(`${API}/api/export/audio-mix`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: video.filename, audio_filename: audio.filename,
          music_volume: musicVolume / 100, original_volume: originalVolume / 100
        })
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Audio mix export failed');
      setVideo({ ...body, original_name: 'Video with background music' });
      setInfo(null); setCaption(null); setCaptionPreview('');
      setMessage('Background music successfully mix ho gaya. Player menu se MP4 save karein.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }


  async function burnCaptions() {
    if (!video || !caption) return;
    setBusy(true); setMessage('Burning subtitles into your video…');
    try {
      const res = await fetch(`${API}/api/export/captions`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: video.filename, subtitle_filename: caption.filename })
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Subtitle export failed');
      setVideo({ ...body, original_name: 'Captioned export' });
      setInfo(null); setCaption(null); setCaptionPreview('');
      setMessage('Captioned video exported. Use the player menu to save it.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  const maxDuration = info?.duration ? Math.max(0.1, info.duration - Number(start || 0)) : 3600;
  const trimEnd = Number(start || 0) + Number(duration || 0);
  const clipDuration = info?.duration || 0;

  return <main className="shell">
    <header><div className="brand"><span className="orb">J</span><div><p className="eyebrow">PERSONAL CREATIVE ASSISTANT</p><h1>JARVIS <em>VIDEO STUDIO</em></h1></div></div><span className="status"><i /> EDITOR READY</span></header>
    <section className="hero"><p className="eyebrow">YOUR IDEAS. YOUR EDIT.</p><h2>Make every second<br/><em>count.</em></h2><p className="sub">Upload, trim, add text and music, use Hindi voice commands, and generate AI subtitles.</p></section>
    <section className="workspace">
      <div className="panel preview"><div className="panel-head"><span>01 / PREVIEW</span><span>LIVE CANVAS</span></div>
        {video ? <video key={timelinePreviewing ? "timeline-" + timelinePreviewIndex : "single-preview"} ref={playerRef} controls playsInline onLoadedMetadata={handleTimelinePreviewLoaded} onTimeUpdate={handleTimelinePreviewTime} onEnded={() => { if (timelinePreviewing) advanceTimelinePreview(); }} src={timelinePreviewing && timelineFiles[timelinePreviewIndex] ? API + timelineFiles[timelinePreviewIndex].url : `${API}${video.url}`} /> : <label className="drop"><input type="file" accept="video/*" onChange={e => setFile(e.target.files?.[0] || null)} /><span className="upload-icon">＋</span><strong>{file ? file.name : 'Choose your video'}</strong><small>MP4, MOV, MKV, WEBM or AVI</small></label>}
        {!video && <button className="primary" disabled={!file || busy} onClick={upload}>{busy ? 'UPLOADING…' : 'UPLOAD & ANALYSE'}</button>}
        {video && <button className="quiet" onClick={() => { setVideo(null); setInfo(null); setFile(null); setCaption(null); setMessage('Choose a video to begin editing.'); }}>Choose another video</button>}
        {waveform && <div className="audio-waveform" aria-label="Audio waveform preview"><div className="waveform-heading"><strong>♫ AUDIO WAVEFORM</strong><span>{waveform.has_audio ? `${waveform.duration}s analysed` : 'NO AUDIO TRACK'}</span></div>{waveform.has_audio ? <div className="waveform-bars">{waveform.samples.map((level, index) => <i key={index} style={{ height: `${Math.max(3, level * 100)}%` }} />)}</div> : <p className="hint">{waveform.error || 'Is video mein audio track nahi hai.'}</p>}{waveform.truncated && <small className="waveform-note">Preview is limited to the first 5 minutes.</small>}</div>}
        {info && <div className="metadata"><span>{info.width} × {info.height}</span><span>{info.duration.toFixed(1)} sec</span><span>{info.video_codec || 'Video'}</span><span>{info.has_audio ? 'Audio ✓' : 'No audio'}</span></div>}
      </div>
      <div className="panel controls"><div className="panel-head"><span>02 / EDIT TOOLS</span><span>QUICK CUT</span></div><h3>Trim your clip</h3><p className="hint">Video analysis detects duration, resolution, codecs and audio automatically.</p>
        {info?.duration > 0 && <div className="visual-trim" aria-label="Visual trim range">
          <div className="visual-trim-labels"><span>0:00</span><strong>SELECTED RANGE</strong><span>{info.duration.toFixed(1)}s</span></div>
          <div className="visual-trim-track">
            <div className="visual-trim-selection" style={{ left: `${Math.min(100, Math.max(0, (Number(start) / clipDuration) * 100))}%`, width: `${Math.max(0, Math.min(100, (trimEnd / clipDuration) * 100) - Math.min(100, Math.max(0, (Number(start) / clipDuration) * 100)))}%` }} />
            <input aria-label="Drag trim start handle" className="trim-range trim-start" type="range" min="0" max={Math.max(0, clipDuration - 0.1)} step="0.1" value={Math.min(Math.max(0, clipDuration - 0.1), Math.max(0, Number(start) || 0))} onChange={e => { const next = Number(e.target.value); setStart(String(next)); if (trimEnd <= next) setDuration(String(Math.max(0.1, clipDuration - next))); }} />
            <input aria-label="Drag trim end handle" className="trim-range trim-end" type="range" min="0.1" max={clipDuration} step="0.1" value={Math.min(clipDuration, Math.max(0.1, trimEnd))} onChange={e => { const next = Number(e.target.value); if (next > Number(start)) setDuration(String((next - Number(start)).toFixed(1))); }} />
          </div>
          <p className="hint">Dono handles ko drag karke video ka start aur end select karein.</p>
        </div>}
        <label>START TIME <div className="input-wrap"><input type="number" min="0" max={info?.duration || 3600} step="0.1" value={start} onChange={e => setStart(e.target.value)} /><span>seconds</span></div></label>
        <label>DURATION <div className="input-wrap"><input type="number" min="0.1" max={maxDuration} step="0.1" value={duration} onChange={e => setDuration(e.target.value)} /><span>seconds</span></div><button type="button" className="quiet" onClick={setTrimStartToPlayhead}>SET START TO PLAYHEAD</button></label>
        <label>END POINT <div className="input-wrap"><span>Seek video, then tap below</span></div><button type="button" className="quiet" onClick={setTrimEndToPlayhead}>SET END TO PLAYHEAD</button></label>
        <button className="primary" disabled={!video || busy} onClick={exportTrim}>{busy ? 'WORKING…' : '✦  EXPORT VIDEO'}</button>
        <div className="voice-box"><h3>03 / JARVIS VOICE COMMAND</h3><p className="hint">Try “start time 5”, “duration 20”, “export video” or “अपलोड”</p><button className="quiet" disabled={busy || listening} onClick={startListening}>{listening ? 'LISTENING…' : '🎙️  SPEAK COMMAND'}</button>{commandText && <small>Heard: {commandText}</small>}</div>
        <div className="voice-box"><h3>04 / AI AUTO CAPTIONS</h3><p className="hint">Whisper creates a downloadable SRT subtitle file.</p><select value={captionLanguage} onChange={e => setCaptionLanguage(e.target.value)}><option value="auto">Detect language</option><option value="hi">Hindi</option><option value="en">English</option></select><button className="quiet" disabled={!video || busy} onClick={generateCaptions}>{busy ? 'PROCESSING…' : 'GENERATE CAPTIONS'}</button>{caption && <><a className="caption-link" href={`${API}${caption.url}`} download>Download subtitles (.srt) · {caption.segments} lines</a><pre className="caption-preview">{captionPreview.slice(0, 1800)}</pre><button className="primary" disabled={busy} onClick={burnCaptions}>BURN CAPTIONS INTO VIDEO</button></>}</div>



        <div className="voice-box fade-box"><h3>07 / FADE EFFECTS</h3><p className="hint">Video aur audio dono smooth tareeke se start aur end honge. Duration seconds mein set karein.</p>
          <label className="volume-control">FADE IN · {Number(fadeIn).toFixed(1)}s<input type="range" min="0" max="10" step="0.5" value={fadeIn} onChange={e => setFadeIn(Number(e.target.value))} disabled={busy} /></label>
          <label className="volume-control">FADE OUT · {Number(fadeOut).toFixed(1)}s<input type="range" min="0" max="10" step="0.5" value={fadeOut} onChange={e => setFadeOut(Number(e.target.value))} disabled={busy} /></label>
          <button className="primary" disabled={!video || busy || (fadeIn === 0 && fadeOut === 0)} onClick={exportFade}>APPLY FADES & EXPORT MP4</button>
        </div>

        <div className="voice-box text-overlay-box"><h3>06 / TEXT OVERLAY</h3><p className="hint">Apna title, naam ya message video par lagayein. Export ke baad text video mein permanently rahega.</p>
          <label className="overlay-label">TEXT TO ADD<textarea rows="3" maxLength="300" value={overlayText} onChange={e => setOverlayText(e.target.value)} placeholder="Yahan apna text likhein…" disabled={busy} /></label>
          <label className="overlay-label">TEXT POSITION<select value={overlayPosition} onChange={e => setOverlayPosition(e.target.value)} disabled={busy}><option value="top">Top center</option><option value="center">Center</option><option value="bottom">Bottom center</option><option value="top-left">Top left</option><option value="top-right">Top right</option><option value="bottom-left">Bottom left</option><option value="bottom-right">Bottom right</option></select></label>
          <label className="volume-control">FONT SIZE · {overlayFontSize}px<input type="range" min="16" max="96" step="2" value={overlayFontSize} onChange={e => setOverlayFontSize(Number(e.target.value))} disabled={busy} /></label>
          <button className="primary" disabled={!video || !overlayText.trim() || busy} onClick={exportTextOverlay}>ADD TEXT & EXPORT MP4</button>
        </div>

        <div className="voice-box music-box"><h3>06 / BACKGROUND MUSIC MIXER</h3><p className="hint">MP3, WAV, M4A, AAC, OGG ya FLAC upload karein. Music video ki length tak loop hoga.</p>
          <label className="music-picker">♫ {musicFile ? musicFile.name : 'CHOOSE BACKGROUND MUSIC'}<input type="file" accept=".mp3,.wav,.aac,.m4a,.ogg,.flac,audio/*" disabled={busy} onChange={e => setMusicFile(e.target.files?.[0] || null)} /></label>
          <label className="volume-control">MUSIC VOLUME · {musicVolume}%<input type="range" min="0" max="200" step="5" value={musicVolume} onChange={e => setMusicVolume(Number(e.target.value))} disabled={busy} /></label>
          <label className="volume-control">ORIGINAL VIDEO AUDIO · {originalVolume}%<input type="range" min="0" max="200" step="5" value={originalVolume} onChange={e => setOriginalVolume(Number(e.target.value))} disabled={busy} /></label>
          <button className="primary" disabled={!video || !musicFile || busy} onClick={exportAudioMix}>MIX MUSIC & EXPORT MP4</button>
        </div>

        <div className="voice-box timeline-box"><h3>05 / MULTI-CLIP TIMELINE</h3><p className="hint">Multiple videos add karein, order badlein aur ek MP4 export karein. Maximum 20 clips.</p>
          <label className="timeline-add">＋ ADD VIDEO CLIPS<input type="file" accept="video/*" multiple disabled={busy} onChange={e => { addTimelineFiles(e.target.files); e.target.value = ''; }} /></label>
          {timelineFiles.length > 0 && <ol className="timeline-list">{timelineFiles.map((clip, index) => <li key={clip.filename}><div className="timeline-clip-main"><strong>{index + 1}. {clip.original_name || clip.filename}</strong><small>Full length: {Number(clip.duration).toFixed(1)} sec</small><div className="timeline-trim"><label>IN <input aria-label={'Clip ' + (index + 1) + ' start'} type="number" min="0" max={clip.duration} step="0.1" value={clip.trimStart} disabled={busy} onChange={e => setTimelineFiles(current => current.map((item, i) => i === index ? { ...item, trimStart: e.target.value } : item))} /></label><label>OUT <input aria-label={'Clip ' + (index + 1) + ' end'} type="number" min="0.1" max={clip.duration} step="0.1" value={clip.trimEnd} disabled={busy} onChange={e => setTimelineFiles(current => current.map((item, i) => i === index ? { ...item, trimEnd: e.target.value } : item))} /></label></div><div className="timeline-visual-trim" aria-label={'Clip ' + (index + 1) + ' visual trim'}>
                <div className="timeline-visual-selection" style={{ left: (Math.min(100, Math.max(0, Number(clip.trimStart) / Number(clip.duration) * 100))) + '%', width: (Math.max(0, Math.min(100, Number(clip.trimEnd) / Number(clip.duration) * 100) - Math.min(100, Math.max(0, Number(clip.trimStart) / Number(clip.duration) * 100)))) + '%' }} />
                <input aria-label={'Clip ' + (index + 1) + ' drag IN handle'} className="timeline-range timeline-range-start" type="range" min="0" max={Math.max(0, Number(clip.trimEnd) - 0.1)} step="0.1" value={Math.min(Math.max(0, Number(clip.trimEnd) - 0.1), Math.max(0, Number(clip.trimStart) || 0))} disabled={busy} onChange={e => setTimelineFiles(current => current.map((item, i) => i === index ? { ...item, trimStart: Number(e.target.value) } : item))} />
                <input aria-label={'Clip ' + (index + 1) + ' drag OUT handle'} className="timeline-range timeline-range-end" type="range" min={Math.min(Number(clip.duration), Number(clip.trimStart) + 0.1)} max={clip.duration} step="0.1" value={Math.min(Number(clip.duration), Math.max(Number(clip.trimStart) + 0.1, Number(clip.trimEnd)))} disabled={busy} onChange={e => setTimelineFiles(current => current.map((item, i) => i === index ? { ...item, trimEnd: Number(e.target.value) } : item))} />
              </div><small>Selected: {Math.max(0, Number(clip.trimEnd) - Number(clip.trimStart)).toFixed(1)} sec</small></div><span className="timeline-actions"><button type="button" className="quiet" disabled={busy || index === 0} onClick={() => moveTimelineClip(index, -1)}>↑</button><button type="button" className="quiet" disabled={busy || index === timelineFiles.length - 1} onClick={() => moveTimelineClip(index, 1)}>↓</button><button type="button" className="quiet" disabled={busy} onClick={() => setTimelineFiles(current => current.filter((_, i) => i !== index))}>×</button></span></li>)}</ol>}
          <button className="quiet" disabled={busy || timelineFiles.length === 0} onClick={startTimelinePreview}>▶ PREVIEW TIMELINE</button>
          <button className="primary" disabled={busy || timelineFiles.length < 2} onClick={exportTimeline}>EXPORT {timelineFiles.length} CLIPS AS ONE VIDEO</button>
        </div>
        <p className="notice" role="status">{message}</p>
      </div>
    </section>
    <footer><span>J.A.R.V.I.S. · VIDEO STUDIO</span><span>BUILD 0.12.0</span></footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);

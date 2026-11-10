import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
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
      setDuration(String(Math.max(0.1, Math.floor(meta.duration * 10) / 10)));
      setCaption(null);
      setMessage('Video analysed. Try a voice command or generate captions.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  async function exportTrim() {
    if (!video) return;
    setBusy(true); setMessage('Rendering your edit…');
    try {
      const res = await fetch(`${API}/api/export/trim`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: video.filename, start: Number(start), duration: Number(duration) })
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.detail || 'Export failed');
      setVideo({ ...body, original_name: 'Edited export' });
      setInfo(null); setCaption(null);
      setMessage('Your edited video is ready. Use the video player menu to save it.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
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

  return <main className="shell">
    <header><div className="brand"><span className="orb">J</span><div><p className="eyebrow">PERSONAL CREATIVE ASSISTANT</p><h1>JARVIS <em>VIDEO STUDIO</em></h1></div></div><span className="status"><i /> EDITOR READY</span></header>
    <section className="hero"><p className="eyebrow">YOUR IDEAS. YOUR EDIT.</p><h2>Make every second<br/><em>count.</em></h2><p className="sub">Upload, inspect, trim, use Hindi voice commands, and generate AI subtitles.</p></section>
    <section className="workspace">
      <div className="panel preview"><div className="panel-head"><span>01 / PREVIEW</span><span>LIVE CANVAS</span></div>
        {video ? <video controls playsInline src={`${API}${video.url}`} /> : <label className="drop"><input type="file" accept="video/*" onChange={e => setFile(e.target.files?.[0] || null)} /><span className="upload-icon">＋</span><strong>{file ? file.name : 'Choose your video'}</strong><small>MP4, MOV, MKV, WEBM or AVI</small></label>}
        {!video && <button className="primary" disabled={!file || busy} onClick={upload}>{busy ? 'UPLOADING…' : 'UPLOAD & ANALYSE'}</button>}
        {video && <button className="quiet" onClick={() => { setVideo(null); setInfo(null); setFile(null); setCaption(null); setMessage('Choose a video to begin editing.'); }}>Choose another video</button>}
        {info && <div className="metadata"><span>{info.width} × {info.height}</span><span>{info.duration.toFixed(1)} sec</span><span>{info.video_codec || 'Video'}</span><span>{info.has_audio ? 'Audio ✓' : 'No audio'}</span></div>}
      </div>
      <div className="panel controls"><div className="panel-head"><span>02 / EDIT TOOLS</span><span>QUICK CUT</span></div><h3>Trim your clip</h3><p className="hint">Video analysis detects duration, resolution, codecs and audio automatically.</p>
        <label>START TIME <div className="input-wrap"><input type="number" min="0" max={info?.duration || 3600} step="0.1" value={start} onChange={e => setStart(e.target.value)} /><span>seconds</span></div></label>
        <label>DURATION <div className="input-wrap"><input type="number" min="0.1" max={maxDuration} step="0.1" value={duration} onChange={e => setDuration(e.target.value)} /><span>seconds</span></div></label>
        <button className="primary" disabled={!video || busy} onClick={exportTrim}>{busy ? 'WORKING…' : '✦  EXPORT VIDEO'}</button>
        <div className="voice-box"><h3>03 / JARVIS VOICE COMMAND</h3><p className="hint">Try “start time 5”, “duration 20”, “export video” or “अपलोड”</p><button className="quiet" disabled={busy || listening} onClick={startListening}>{listening ? 'LISTENING…' : '🎙️  SPEAK COMMAND'}</button>{commandText && <small>Heard: {commandText}</small>}</div>
        <div className="voice-box"><h3>04 / AI AUTO CAPTIONS</h3><p className="hint">Whisper creates a downloadable SRT subtitle file.</p><select value={captionLanguage} onChange={e => setCaptionLanguage(e.target.value)}><option value="auto">Detect language</option><option value="hi">Hindi</option><option value="en">English</option></select><button className="quiet" disabled={!video || busy} onClick={generateCaptions}>{busy ? 'PROCESSING…' : 'GENERATE CAPTIONS'}</button>{caption && <><a className="caption-link" href={`${API}${caption.url}`} download>Download subtitles (.srt) · {caption.segments} lines</a><pre className="caption-preview">{captionPreview.slice(0, 1800)}</pre><button className="primary" disabled={busy} onClick={burnCaptions}>BURN CAPTIONS INTO VIDEO</button></>}</div>
        <p className="notice" role="status">{message}</p>
      </div>
    </section>
    <footer><span>J.A.R.V.I.S. · VIDEO STUDIO</span><span>BUILD 0.4.0</span></footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);

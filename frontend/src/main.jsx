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
      setMessage('Video analysed. Adjust the start time and export your clip.');
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
      setInfo(null);
      setMessage('Your edited video is ready. Use the video player menu to save it.');
    } catch (err) { setMessage(err.message); }
    finally { setBusy(false); }
  }

  const maxDuration = info?.duration ? Math.max(0.1, info.duration - Number(start || 0)) : 3600;

  return <main className="shell">
    <header><div className="brand"><span className="orb">J</span><div><p className="eyebrow">PERSONAL CREATIVE ASSISTANT</p><h1>JARVIS <em>VIDEO STUDIO</em></h1></div></div><span className="status"><i /> EDITOR READY</span></header>
    <section className="hero"><p className="eyebrow">YOUR IDEAS. YOUR EDIT.</p><h2>Make every second<br/><em>count.</em></h2><p className="sub">A mobile-friendly video editing workspace. Upload a clip, inspect its details, trim it, and export your edit.</p></section>
    <section className="workspace">
      <div className="panel preview"><div className="panel-head"><span>01 / PREVIEW</span><span>LIVE CANVAS</span></div>
        {video ? <video controls playsInline src={`${API}${video.url}`} /> : <label className="drop"><input type="file" accept="video/*" onChange={e => setFile(e.target.files?.[0] || null)} /><span className="upload-icon">＋</span><strong>{file ? file.name : 'Choose your video'}</strong><small>MP4, MOV, MKV, WEBM or AVI</small></label>}
        {!video && <button className="primary" disabled={!file || busy} onClick={upload}>{busy ? 'UPLOADING…' : 'UPLOAD & ANALYSE'}</button>}
        {video && <button className="quiet" onClick={() => { setVideo(null); setInfo(null); setFile(null); setMessage('Choose a video to begin editing.'); }}>Choose another video</button>}
        {info && <div className="metadata"><span>{info.width} × {info.height}</span><span>{info.duration.toFixed(1)} sec</span><span>{info.video_codec || 'Video'}</span><span>{info.has_audio ? 'Audio ✓' : 'No audio'}</span></div>}
      </div>
      <div className="panel controls"><div className="panel-head"><span>02 / EDIT TOOLS</span><span>QUICK CUT</span></div><h3>Trim your clip</h3><p className="hint">Video analysis now detects duration, resolution, codecs and audio automatically.</p>
        <label>START TIME <div className="input-wrap"><input type="number" min="0" max={info?.duration || 3600} step="0.1" value={start} onChange={e => setStart(e.target.value)} /><span>seconds</span></div></label>
        <label>DURATION <div className="input-wrap"><input type="number" min="0.1" max={maxDuration} step="0.1" value={duration} onChange={e => setDuration(e.target.value)} /><span>seconds</span></div></label>
        <button className="primary" disabled={!video || busy} onClick={exportTrim}>{busy ? 'WORKING…' : '✦  EXPORT VIDEO'}</button>
        <p className="notice" role="status">{message}</p>
      </div>
    </section>
    <footer><span>J.A.R.V.I.S. · VIDEO STUDIO</span><span>BUILD 0.2.0</span></footer>
  </main>;
}

createRoot(document.getElementById('root')).render(<App />);

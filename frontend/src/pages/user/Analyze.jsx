import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api'
import { usePage } from '../../layout'
import { Alert, Button, Field, Spinner, useToast } from '../../ui'

const MIN_WORDS = 20
const MAX_MB = 10

export default function Analyze() {
  usePage([{ label: 'Dashboard', to: '/dashboard' }, { label: 'Analyze news' }])
  const nav = useNavigate(); const toast = useToast()
  const [mode, setMode] = useState('paste')
  const [title, setTitle] = useState(''); const [text, setText] = useState(''); const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false); const [err, setErr] = useState(''); const [over, setOver] = useState(false)
  const inputRef = useRef(null)
  const words = text.trim() ? text.trim().split(/\s+/).length : 0

  const pick = (f) => {
    setErr('')
    if (!f) return
    const ext = f.name.split('.').pop().toLowerCase()
    if (!['txt', 'pdf'].includes(ext)) return setErr(`Invalid file format ".${ext}". Upload a .txt or .pdf file.`)
    if (f.size > MAX_MB * 1024 * 1024) return setErr(`The file is too large (maximum ${MAX_MB} MB).`)
    setFile(f)
  }
  const clear = () => { setTitle(''); setText(''); setFile(null); setErr(''); if (inputRef.current) inputRef.current.value = '' }

  const analyze = async () => {
    setErr('')
    if (mode === 'paste' && words < MIN_WORDS) return setErr(`Add at least ${MIN_WORDS} words so the model has enough to work with (you have ${words}).`)
    if (mode === 'upload' && !file) return setErr('Choose a .txt or .pdf file first.')
    setBusy(true)
    try {
      const res = mode === 'paste' ? await api.post('/api/news/analyze', { title: title.trim() || null, text }) : await api.upload('/api/news/upload', file)
      toast('Prediction completed', 'ok')
      nav(`/results/${res.prediction_id}`)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="stack" style={{ maxWidth: 860 }}>
      <div><h1>Analyze a news article</h1><p className="muted">Paste the text or upload a document. You get a prediction, a confidence score, and the words that drove it.</p></div>
      <div className="panel">
        <div className="tabs" role="tablist">
          {[['paste', 'Paste text'], ['upload', 'Upload document']].map(([k, l]) => (
            <a key={k} role="tab" aria-selected={mode === k} href="#" className={mode === k ? 'active' : ''} onClick={(e) => { e.preventDefault(); setMode(k); setErr('') }}>{l}</a>))}
        </div>
        <Alert>{err}</Alert>
        {mode === 'paste' ? (<>
          <Field label="Headline (optional)" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={500} />
          <Field label="Article text" id="article-text" hint={`${text.length.toLocaleString()} characters, ${words.toLocaleString()} words${words < MIN_WORDS ? ` (minimum ${MIN_WORDS})` : ''}`}>
            <textarea id="article-text" className="editor" value={text} onChange={(e) => setText(e.target.value)} placeholder="Paste the full article here..." />
          </Field>
        </>) : (
          <div className={`drop ${over ? 'over' : ''}`} tabIndex={0} role="button" aria-label="Choose a file to upload"
            onClick={() => inputRef.current?.click()} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
            onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files[0]) }}>
            <input ref={inputRef} type="file" accept=".txt,.pdf" hidden onChange={(e) => pick(e.target.files[0])} />
            {file ? <><strong>{file.name}</strong><br /><span className="small">{(file.size / 1024).toFixed(0)} KB. Click to choose a different file.</span></> : <>Drop a .txt or .pdf file here, or click to browse.<br /><span className="small">Maximum {MAX_MB} MB. Scanned PDFs without text cannot be read.</span></>}
          </div>)}
        <div className="row" style={{ marginTop: '1.2rem' }}>
          <Button onClick={analyze} loading={busy}>{busy ? 'Analyzing...' : 'Analyze'}</Button>
          <Button variant="secondary" onClick={clear} disabled={busy}>Clear</Button>
        </div>
        {busy && <p className="muted small" style={{ marginTop: '.8rem' }}><Spinner /> Preprocessing, classifying, explaining and finding similar articles. This usually takes a few seconds.</p>}
      </div>
      <Alert kind="warn">This tool estimates how closely an article resembles known fake or real news. It is a decision-support aid, not a verdict on truth.</Alert>
    </div>
  )
}

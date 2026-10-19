import { useEffect, useState } from 'react'
import { api } from '../../api'
import { usePage } from '../../layout'
import { Alert, Button, Field, Loading, useFetch, useToast } from '../../ui'

export default function Settings() {
  usePage([{ label: 'Administration', to: '/admin' }, { label: 'Settings' }])
  const toast = useToast()
  const s = useFetch(() => api.get('/api/admin/settings'))
  const models = useFetch(() => api.get('/api/admin/models'))
  const sw = useFetch(() => api.get('/api/admin/stopwords'))
  const kd = useFetch(() => api.get('/api/admin/keyword-dictionary'))
  const [v, setV] = useState(null); const [words, setWords] = useState(''); const [term, setTerm] = useState(''); const [type, setType] = useState('include'); const [err, setErr] = useState('')
  useEffect(() => { if (s.data) setV(s.data.values) }, [s.data])
  useEffect(() => { if (sw.data) setWords(sw.data.words.join('\n')) }, [sw.data])
  if (s.loading || !v) return <Loading />
  const run = async (fn, ok) => { setErr(''); try { await fn(); ok && toast(ok, 'ok') } catch (e) { setErr(e.message) } }
  const set = (k) => (e) => setV({ ...v, [k]: e.target.value })
  const ready = models.data?.items.filter((m) => m.status === 'Ready') || []
  const types = new Set(v.supported_file_types.split(',').map((t) => t.trim()))
  const toggleType = (t) => { const n = new Set(types); n.has(t) ? n.delete(t) : n.add(t); setV({ ...v, supported_file_types: [...n].join(',') }) }
  return (
    <div className="stack" style={{ maxWidth: 900 }}>
      <h1>System settings</h1><Alert>{err}</Alert>
      <div className="panel"><h2>Default NLP model</h2>
        <p className="muted">The model used for every user analysis. Only one can be active.</p>
        <div className="row"><select aria-label="Active model" style={{ maxWidth: 420 }} value={s.data.default_nlp_model || ''} onChange={(e) => run(async () => { await api.put(`/api/admin/models/${e.target.value}/activate`); s.reload(); models.reload() }, 'Model activated')}>
          <option value="" disabled>No active model</option>{ready.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select></div></div>

      <div className="panel"><h2>Analysis and uploads</h2>
        <div className="grid g2">
          <Field label="Maximum upload size (MB)" type="number" min="1" max="100" value={v.max_upload_mb} onChange={set('max_upload_mb')} />
          <Field label="Keyword extraction method" id="s-kw"><select id="s-kw" value={v.keyword_method} onChange={set('keyword_method')}>{s.data.keyword_methods.map((m) => <option key={m} value={m}>{m === 'tfidf' ? 'TF-IDF' : 'RAKE'}</option>)}</select></Field>
          <Field label="Keywords shown per article" type="number" min="1" max="30" value={v.keywords_top_n} onChange={set('keywords_top_n')} />
          <Field label="Dataset used for training" id="s-ds"><select id="s-ds" value={v.active_dataset} onChange={set('active_dataset')}><option value="all">All imported datasets</option>{s.data.datasets.map((d) => <option key={d.dataset_id} value={d.dataset_id}>v{d.dataset_id}: {d.name}</option>)}</select></Field>
        </div>
        <Field label="Supported file types" id="s-types"><div className="row">{['txt', 'pdf'].map((t) => <label key={t} className="row"><input type="checkbox" checked={types.has(t)} onChange={() => toggleType(t)} /> .{t}</label>)}</div></Field>
        <Field label="Default theme for new visitors" id="s-theme"><select id="s-theme" value={v.theme} onChange={set('theme')}><option value="light">Light</option><option value="dark">Dark</option></select></Field>
        <Button onClick={() => run(async () => { await api.put('/api/admin/settings', { values: Object.fromEntries(Object.entries(v).map(([k, x]) => [k, String(x)])) }) }, 'Settings saved')}>Save settings</Button>
        <p className="hint">New and retrained models use the dataset chosen here. The default theme applies to visitors who have not picked one themselves.</p></div>

      <div className="panel"><h2>Stop-word list</h2>
        <p className="muted">One word per line. Saved changes apply to new predictions only after you retrain a model, so training and prediction stay consistent.</p>
        <textarea aria-label="Stop words" rows={10} value={words} onChange={(e) => setWords(e.target.value)} />
        <div className="row" style={{ marginTop: '.8rem' }}><Button onClick={() => run(async () => { const r = await api.put('/api/admin/stopwords', { words: words.split(/\s+/) }); toast(r.message, 'ok'); sw.reload() })}>Save stop words</Button><span className="muted small">{words.split(/\s+/).filter(Boolean).length} words</span></div></div>

      <div className="panel"><h2>Keyword dictionary</h2>
        <p className="muted">Include terms are always shown when they appear in an article. Exclude terms are never shown as keywords.</p>
        <div className="row" style={{ marginBottom: '1rem' }}>
          <input aria-label="New dictionary term" style={{ maxWidth: 260 }} placeholder="Term" value={term} onChange={(e) => setTerm(e.target.value)} />
          <select aria-label="List" style={{ width: 'auto' }} value={type} onChange={(e) => setType(e.target.value)}><option value="include">Include</option><option value="exclude">Exclude</option></select>
          <Button disabled={!term.trim()} onClick={() => run(async () => { await api.post('/api/admin/keyword-dictionary', { term, list_type: type }); setTerm(''); kd.reload() }, 'Term added')}>Add term</Button></div>
        {kd.data && (['include', 'exclude'].map((t) => (<div key={t}><h3>{t === 'include' ? 'Always include' : 'Always exclude'}</h3>
          {kd.data.items.filter((e) => e.list_type === t).length === 0 ? <p className="muted small">None.</p> : kd.data.items.filter((e) => e.list_type === t).map((e) => <span className="kw" key={e.id}>{e.term} <button className="btn ghost sm" aria-label={`Remove ${e.term}`} onClick={() => run(async () => { await api.del(`/api/admin/keyword-dictionary/${e.id}`); kd.reload() })}>Remove</button></span>)}</div>)))}</div>
    </div>
  )
}

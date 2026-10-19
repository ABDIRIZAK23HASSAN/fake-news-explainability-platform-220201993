import { useEffect, useRef, useState } from 'react'
import { api } from '../../api'
import { usePage } from '../../layout'
import { Alert, Button, Empty, fmtDate, Loading, useConfirm, useFetch, useToast } from '../../ui'

const statusTone = { Success: 'real', Failed: 'fake', Processing: 'warn' }

export default function Datasets() {
  usePage([{ label: 'Administration', to: '/admin' }, { label: 'Datasets' }])
  const toast = useToast(); const confirm = useConfirm(); const fileRef = useRef(null)
  const [file, setFile] = useState(null); const [preview, setPreview] = useState(null); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false); const [jobId, setJobId] = useState(null); const [job, setJob] = useState(null)
  const { data, loading, reload } = useFetch(() => api.get('/api/admin/datasets'))

  useEffect(() => {                                // poll the import progress
    if (!jobId) return
    const t = setInterval(async () => {
      try { const j = await api.get(`/api/admin/datasets/${jobId}`); setJob(j)
        if (j.status !== 'Processing') { clearInterval(t); setJobId(null); reload(); toast(j.status === 'Success' ? 'Dataset imported successfully' : 'Dataset import failed', j.status === 'Success' ? 'ok' : 'error') }
      } catch { clearInterval(t) }
    }, 1200)
    return () => clearInterval(t)
  }, [jobId])      // eslint-disable-line

  const choose = async (f) => {
    setErr(''); setPreview(null); setJob(null); setFile(f)
    if (!f) return
    if (!f.name.toLowerCase().endsWith('.csv')) { setFile(null); return setErr('Invalid file format. Only .csv datasets are accepted.') }
    setBusy(true)
    try { setPreview(await api.upload('/api/admin/datasets/preview', f)) } catch (e) { setErr(e.message); setFile(null) } finally { setBusy(false) }
  }
  const doImport = async () => {
    setBusy(true); setErr('')
    try { const r = await api.upload('/api/admin/datasets/upload', file); setJob(r); setJobId(r.dataset_id); setPreview(null); setFile(null); if (fileRef.current) fileRef.current.value = '' }
    catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const remove = async (d) => {
    if (!(await confirm({ title: 'Delete dataset', message: `Delete "${d.name}" and its ${d.imported_records.toLocaleString()} articles? Models already trained are not affected.`, confirmLabel: 'Delete dataset' }))) return
    try { await api.del(`/api/admin/datasets/${d.dataset_id}`); toast('Dataset deleted', 'ok'); reload() } catch (e) { toast(e.message, 'error') }
  }

  return (
    <div className="stack">
      <h1>Datasets</h1>
      <div className="panel">
        <h2>Import a CSV dataset</h2>
        <p className="muted">Required columns: <code>title, text, subject, date, label</code>. Label values: Fake/Real or 0/1. The file is checked first; nothing is stored until you confirm.</p>
        <Alert>{err}</Alert>
        <input ref={fileRef} type="file" accept=".csv" onChange={(e) => choose(e.target.files[0])} aria-label="Dataset CSV file" />
        {busy && !job && <p className="muted"><span className="spinner" /> Checking the file...</p>}
        {preview && (
          <div className="stack" style={{ marginTop: '1rem' }}>
            <div className="grid g4">
              <div className="stat"><div className="v">{preview.total.toLocaleString()}</div><div className="l">Rows in file</div></div>
              <div className="stat real"><div className="v">{preview.would_import.toLocaleString()}</div><div className="l">Will be imported</div></div>
              <div className="stat fake"><div className="v">{preview.rejected.toLocaleString()}</div><div className="l">Invalid, rejected</div></div>
              <div className="stat"><div className="v">{preview.duplicates.toLocaleString()}</div><div className="l">Duplicates, ignored ({preview.duplicates_in_file} in file, {preview.duplicates_in_database} already stored)</div></div>
            </div>
            {Object.keys(preview.reject_reasons).length > 0 && <Alert kind="warn">Rejected rows: {Object.entries(preview.reject_reasons).map(([k, v]) => `${v} with ${k}`).join('; ')}.</Alert>}
            <div className="table-wrap"><table><thead><tr>{preview.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>{preview.sample_rows.slice(0, 5).map((r, i) => <tr key={i}>{preview.columns.map((c) => <td key={c} style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(r[c]).slice(0, 90)}</td>)}</tr>)}</tbody></table></div>
            <div className="row"><Button onClick={doImport} loading={busy} disabled={!preview.would_import}>Import {preview.would_import.toLocaleString()} articles</Button><Button variant="secondary" onClick={() => { setPreview(null); setFile(null); fileRef.current.value = '' }}>Cancel</Button></div>
          </div>)}
        {job && job.status === 'Processing' && (
          <div style={{ marginTop: '1rem' }}><p>Importing "{job.name}" ({job.progress}%). Preprocessing every article so it can be used for training right away...</p>
            <div className="progress" role="progressbar" aria-valuenow={job.progress} aria-valuemin={0} aria-valuemax={100}><div style={{ width: `${job.progress}%` }} /></div></div>)}
        {job && job.status !== 'Processing' && <Alert kind={job.status === 'Success' ? 'ok' : 'error'}>{job.status === 'Success' ? `Imported ${job.imported_records.toLocaleString()} articles; ${job.rejected_records.toLocaleString()} rejected; ${job.duplicate_records.toLocaleString()} duplicates ignored.` : job.message}</Alert>}
      </div>

      <div className="panel">
        <div className="row between"><h2 style={{ margin: 0 }}>Import history</h2>{data && <span className="muted small">{data.total_articles.toLocaleString()} articles stored in total</span>}</div>
        {loading ? <Loading /> : !data.items.length ? <Empty title="No datasets imported yet"><p>Import Fake.csv and True.csv (with a label column) to begin.</p></Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Version</th><th>File</th><th>Uploaded</th><th>Total</th><th>Imported</th><th>Rejected</th><th>Duplicates</th><th>Status</th><th /></tr></thead>
            <tbody>{data.items.map((d) => <tr key={d.dataset_id}><td>v{d.dataset_id}</td><td>{d.name}</td><td className="nowrap">{fmtDate(d.upload_date)}</td><td>{d.total_records.toLocaleString()}</td><td>{d.imported_records.toLocaleString()}</td><td>{d.rejected_records.toLocaleString()}</td><td>{d.duplicate_records.toLocaleString()}</td>
              <td><span className={`badge ${statusTone[d.status] || 'neutral'}`}>{d.status}</span>{d.message && <div className="small muted" style={{ maxWidth: 240 }}>{d.message}</div>}</td>
              <td><Button variant="ghost" small onClick={() => remove(d)} disabled={d.status === 'Processing'}>Delete</Button></td></tr>)}</tbody></table></div>)}
      </div>
    </div>
  )
}

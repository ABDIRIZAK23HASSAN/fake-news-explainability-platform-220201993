import { useEffect, useState } from 'react'
import { api } from '../../api'
import { ChartBox, useThemeColors } from '../../components'
import { usePage } from '../../layout'
import { Alert, Button, Empty, Field, fmtDate, Loading, Modal, pct, useConfirm, useFetch, useToast } from '../../ui'

const tone = { Ready: 'real', Failed: 'fake', Training: 'warn' }

function Details({ id, onClose }) {
  const { data: m, loading } = useFetch(() => api.get(`/api/admin/models/${id}`), [id])
  const c = useThemeColors()
  return (
    <Modal wide title="Model details" onClose={onClose}>
      {loading ? <Loading /> : (<>
        <p><strong>{m.name}</strong><br /><span className="muted small">{m.algorithm}, {m.vectorizer}, dataset: {m.dataset_version || '-'}</span></p>
        {m.confusion_matrix && <><h3>Confusion matrix (test set)</h3>
          <table style={{ maxWidth: 420 }}><thead><tr><th /><th>Predicted fake</th><th>Predicted real</th></tr></thead>
            <tbody><tr><th>Actually fake</th><td>{m.confusion_matrix[0][0].toLocaleString()}</td><td>{m.confusion_matrix[0][1].toLocaleString()}</td></tr>
              <tr><th>Actually real</th><td>{m.confusion_matrix[1][0].toLocaleString()}</td><td>{m.confusion_matrix[1][1].toLocaleString()}</td></tr></tbody></table></>}
        <h3 style={{ marginTop: '1rem' }}>ROC curve (test set)</h3>
        {m.roc_curve ? <>
          <ChartBox type="line" height={260} data={{ datasets: [
            { label: `${m.algorithm.replace('_', ' ')} (AUC ${m.roc_auc?.toFixed(4)})`, data: m.roc_curve.fpr.map((x, i) => ({ x, y: m.roc_curve.tpr[i] })), borderColor: c.navy, backgroundColor: c.navy, pointRadius: 0, borderWidth: 2 },
            { label: 'Random guessing', data: [{ x: 0, y: 0 }, { x: 1, y: 1 }], borderColor: c.soft, borderDash: [6, 4], pointRadius: 0, borderWidth: 1 }] }}
            options={{ scales: { x: { type: 'linear', min: 0, max: 1, title: { display: true, text: 'False positive rate', color: c.soft }, ticks: { color: c.soft }, grid: { color: c.line } },
                                 y: { min: 0, max: 1, title: { display: true, text: 'True positive rate', color: c.soft }, ticks: { color: c.soft }, grid: { color: c.line } } } }} />
          <p className="hint">Curves of strong models hug the top-left corner and look alike; the AUC column in the table gives the numbers.</p></>
          : <p className="muted small">No ROC curve is stored for this model. Retrain it to generate one.</p>}
        <h3 style={{ marginTop: '1rem' }}>Training logs</h3>
        {!m.runs.length ? <p className="muted">No training runs recorded.</p> : m.runs.map((r) => <div key={r.run_id}><p className="small muted">Run #{r.run_id}, {fmtDate(r.started_at)}, {r.status}{r.duration ? `, ${r.duration}s` : ''}{r.n_train ? `, ${r.n_train.toLocaleString()} train / ${r.n_test.toLocaleString()} test` : ''}</p><pre className="log">{r.log || '(no log)'}</pre></div>)}
      </>)}
    </Modal>
  )
}

export default function Models() {
  usePage([{ label: 'Administration', to: '/admin' }, { label: 'Models' }])
  const toast = useToast(); const confirm = useConfirm(); const c = useThemeColors()
  const opts = useFetch(() => api.get('/api/admin/models/options'))
  const { data, loading, reload } = useFetch(() => api.get('/api/admin/models'))
  const runs = useFetch(() => api.get('/api/admin/models/runs'))
  const [form, setForm] = useState({ algorithm: 'logistic_regression', vectorizer: 'tfidf_bigram', name: '' }); const [busy, setBusy] = useState(false); const [detail, setDetail] = useState(null)
  const training = data?.items.some((m) => m.status === 'Training')
  useEffect(() => { if (!training) return; const t = setInterval(() => { reload(); runs.reload() }, 3000); return () => clearInterval(t) }, [training])   // eslint-disable-line
  const act = async (fn, ok) => { setBusy(true); try { await fn(); ok && toast(ok, 'ok'); reload(); runs.reload() } catch (e) { toast(e.message, 'error') } finally { setBusy(false) } }
  const ready = data?.items.filter((m) => m.status === 'Ready') || []

  return (
    <div className="stack">
      <h1>Machine learning models</h1>
      {training && <Alert kind="warn"><span className="spinner" /> A model is training. This page refreshes by itself; large datasets can take several minutes.</Alert>}
      <div className="panel">
        <h2>Train a model</h2>
        <p className="muted">Trains on the stored dataset (80% train, 20% held-out test) and records accuracy, precision, recall, F1 and ROC-AUC.</p>
        <div className="grid g3">
          <Field label="Algorithm" id="m-algo"><select id="m-algo" value={form.algorithm} onChange={(e) => setForm({ ...form, algorithm: e.target.value })}>{opts.data && Object.entries(opts.data.algorithms).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></Field>
          <Field label="Feature extraction" id="m-vec"><select id="m-vec" value={form.vectorizer} onChange={(e) => setForm({ ...form, vectorizer: e.target.value })}>{opts.data?.vectorizers.map((v) => <option key={v}>{v}</option>)}</select></Field>
          <Field label="Name (optional)" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div className="row"><Button loading={busy} disabled={training} onClick={() => act(() => api.post('/api/admin/models/train', form), 'Training started')}>Train model</Button>
          <Button variant="secondary" disabled={training || busy} onClick={async () => { if (await confirm({ title: 'Compare all algorithms', message: 'Train every available algorithm one after another so you can compare them? This can take several minutes.', confirmLabel: 'Train all', danger: false })) act(() => api.post('/api/admin/models/train-batch', { algorithms: Object.keys(opts.data.algorithms), vectorizer: form.vectorizer }), 'Training all algorithms') }}>Train and compare all algorithms</Button></div>
      </div>

      <div className="panel">
        <h2>Trained models</h2>
        {loading ? <Loading /> : !data.items.length ? <Empty title="No models yet"><p>Train one above, then activate it so users can analyze articles.</p></Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Model</th><th>Accuracy</th><th>Precision</th><th>Recall</th><th>F1</th><th>ROC-AUC</th><th>Train time</th><th>Status</th><th /></tr></thead>
            <tbody>{data.items.map((m) => (
              <tr key={m.id}><td style={{ maxWidth: 260 }}>{m.name} {m.is_active && <span className="badge real">Active</span>}<div className="small muted">{m.dataset_version}</div></td>
                <td>{pct(m.accuracy, 2)}</td><td>{pct(m.precision, 2)}</td><td>{pct(m.recall, 2)}</td><td>{pct(m.f1, 2)}</td><td>{m.roc_auc?.toFixed(4) ?? '-'}</td><td>{m.training_seconds ? `${m.training_seconds}s` : '-'}</td>
                <td><span className={`badge ${tone[m.status] || 'neutral'}`}>{m.status}</span></td>
                <td className="nowrap">
                  <Button variant="ghost" small onClick={() => setDetail(m.id)}>Details</Button>
                  {m.status === 'Ready' && !m.is_active && <Button variant="ghost" small disabled={busy} onClick={() => act(() => api.put(`/api/admin/models/${m.id}/activate`), 'Model activated')}>Activate</Button>}
                  {m.status !== 'Training' && <Button variant="ghost" small disabled={busy || training} onClick={async () => { if (await confirm({ title: 'Retrain model', message: 'Retrain this model on the current dataset? Its metrics will be replaced.', confirmLabel: 'Retrain', danger: false })) act(() => api.post(`/api/admin/models/${m.id}/retrain`), 'Retraining started') }}>Retrain</Button>}
                  {!m.is_active && m.status !== 'Training' && <Button variant="ghost" small disabled={busy} onClick={async () => { if (await confirm({ title: 'Delete model', message: `Delete "${m.name}"? Predictions made with it stay in users' history.`, confirmLabel: 'Delete' })) act(() => api.del(`/api/admin/models/${m.id}`), 'Model deleted') }}>Delete</Button>}</td></tr>))}</tbody></table></div>)}
      </div>

      {ready.length > 1 && <div className="panel"><h2>Model comparison</h2>
        <ChartBox type="bar" data={{ labels: ready.map((m) => m.algorithm.replace('_', ' ')), datasets: ['accuracy', 'precision', 'recall', 'f1'].map((k, i) => ({ label: k, data: ready.map((m) => m[k]), backgroundColor: [c.navy, c.soft, c.real, c.fake][i] })) }}
          options={{ scales: { y: { min: 0.9, max: 1 } } }} />
        <p className="hint">The vertical axis starts at 90% to make small differences visible. Differences of a few tenths of a point are within the noise of a single train/test split.</p></div>}

      <div className="panel"><h2>Training history</h2>
        {runs.loading ? <Loading /> : !runs.data.items.length ? <p className="muted">No training runs yet.</p> : <div className="table-wrap"><table>
          <thead><tr><th>Run</th><th>Model</th><th>Started</th><th>Duration</th><th>Dataset version</th><th>Train / test</th><th>Status</th></tr></thead>
          <tbody>{runs.data.items.map((r) => <tr key={r.run_id}><td>#{r.run_id}</td><td>#{r.model_id}</td><td className="nowrap">{fmtDate(r.started_at)}</td><td>{r.duration ? `${r.duration}s` : '-'}</td><td className="small">{r.dataset_version}</td><td>{r.n_train ? `${r.n_train.toLocaleString()} / ${r.n_test.toLocaleString()}` : '-'}</td><td><span className={`badge ${r.status === 'Completed' ? 'real' : r.status === 'Failed' ? 'fake' : 'warn'}`}>{r.status}</span></td></tr>)}</tbody></table></div>}
      </div>
      {detail && <Details id={detail} onClose={() => setDetail(null)} />}
    </div>
  )
}

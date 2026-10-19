import { useState } from 'react'
import { api } from '../../api'
import { usePage } from '../../layout'
import { Alert, Button, Empty, Field, LabelBadge, Loading, Modal, Pagination, useConfirm, useDebounced, useFetch, useToast } from '../../ui'

function ArticleModal({ id, edit, onClose, onSaved }) {
  const { data: a, error, loading } = useFetch(() => api.get(`/api/admin/news/${id}`), [id])
  const [f, setF] = useState(null); const [err, setErr] = useState(''); const [busy, setBusy] = useState(false)
  const cur = f || a
  const save = async () => { setBusy(true); setErr(''); try { await api.put(`/api/admin/news/${id}`, { title: cur.title, content: cur.content, subject: cur.subject, label: cur.label, publication_date: cur.publication_date }); onSaved() } catch (e) { setErr(e.message) } finally { setBusy(false) } }
  const set = (k) => (e) => setF({ ...cur, [k]: e.target.value })
  return (
    <Modal wide title={edit ? 'Edit article' : 'Article details'} onClose={onClose}>
      {loading ? <Loading /> : error ? <Alert>{error}</Alert> : (<>
        <Alert>{err}</Alert>
        {edit ? (<>
          <Field label="Title" value={cur.title} onChange={set('title')} />
          <div className="grid g3"><Field label="Subject" value={cur.subject} onChange={set('subject')} /><Field label="Label" id="a-label"><select id="a-label" value={cur.label} onChange={set('label')}><option>Fake</option><option>Real</option></select></Field><Field label="Publication date" value={cur.publication_date || ''} onChange={set('publication_date')} /></div>
          <Field label="Content" id="a-content"><textarea id="a-content" rows={12} value={cur.content} onChange={set('content')} /></Field>
          <p className="hint">Changing the text re-processes this article the next time a model is trained.</p>
          <div className="row" style={{ justifyContent: 'flex-end' }}><Button variant="secondary" onClick={onClose}>Cancel</Button><Button loading={busy} onClick={save}>Save changes</Button></div></>) : (<>
          <div className="row"><LabelBadge label={a.label} /><span className="muted small">{a.subject}, {a.publication_date || 'no date'}, from {a.source_file} (dataset v{a.dataset_id})</span></div>
          <h3 style={{ marginTop: '.8rem' }}>{a.title}</h3><div className="article" style={{ fontSize: '1rem' }}>{a.content}</div></>)}
      </>)}
    </Modal>
  )
}

export default function News() {
  usePage([{ label: 'Administration', to: '/admin' }, { label: 'News articles' }])
  const toast = useToast(); const confirm = useConfirm()
  const [q, setQ] = useState(''); const [label, setLabel] = useState(''); const [subject, setSubject] = useState(''); const [page, setPage] = useState(1); const [modal, setModal] = useState(null); const [rename, setRename] = useState(null)
  const dq = useDebounced(q)
  const subjects = useFetch(() => api.get('/api/admin/subjects'))
  const { data, error, loading, reload } = useFetch(() => api.get('/api/admin/news', { search: dq, label, subject, page, page_size: 10 }), [dq, label, subject, page])
  const del = async (a) => { if (await confirm({ title: 'Delete article', message: `Delete "${a.title.slice(0, 80)}"? It will no longer be used for training or similarity search.`, confirmLabel: 'Delete article' })) { try { await api.del(`/api/admin/news/${a.news_id}`); toast('Article deleted', 'ok'); reload(); subjects.reload() } catch (e) { toast(e.message, 'error') } } }
  const doRename = async () => { try { const r = await api.put(`/api/admin/subjects/${encodeURIComponent(rename.name)}`, { new_name: rename.to }); toast(`${r.updated} articles updated`, 'ok'); setRename(null); subjects.reload(); reload() } catch (e) { toast(e.message, 'error') } }
  return (
    <div className="stack">
      <h1>News articles</h1>
      <div className="panel">
        <div className="row" style={{ marginBottom: '1rem' }}>
          <div className="grow" style={{ minWidth: 220 }}><input type="search" placeholder="Search titles and text" aria-label="Search articles" value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} /></div>
          <select aria-label="Filter by label" style={{ width: 'auto' }} value={label} onChange={(e) => { setLabel(e.target.value); setPage(1) }}><option value="">Fake and real</option><option>Fake</option><option>Real</option></select>
          <select aria-label="Filter by category" style={{ width: 'auto' }} value={subject} onChange={(e) => { setSubject(e.target.value); setPage(1) }}><option value="">All categories</option>{subjects.data?.items.map((s) => <option key={s.subject}>{s.subject}</option>)}</select>
        </div>
        {error && <Alert>{error}</Alert>}
        {loading && !data ? <Loading /> : data && !data.items.length ? <Empty title="No articles match your filters" /> : data && (<>
          <div className="table-wrap"><table><thead><tr><th>Title</th><th>Category</th><th>Label</th><th>Published</th><th /></tr></thead>
            <tbody>{data.items.map((a) => <tr key={a.news_id}><td style={{ maxWidth: 420 }}>{a.title}</td><td>{a.subject}</td><td><LabelBadge label={a.label} /></td><td className="nowrap">{a.publication_date}</td>
              <td className="nowrap"><Button variant="ghost" small onClick={() => setModal({ id: a.news_id })}>View</Button><Button variant="ghost" small onClick={() => setModal({ id: a.news_id, edit: true })}>Edit</Button><Button variant="ghost" small onClick={() => del(a)}>Delete</Button></td></tr>)}</tbody></table></div>
          <div className="row between"><span className="muted small">{data.total.toLocaleString()} articles</span><Pagination page={data.page} pages={data.pages} onPage={setPage} /></div></>)}
      </div>
      <div className="panel"><h2>Subject categories</h2>
        <p className="muted">Rename a category to fix it. Renaming onto an existing name merges the two.</p>
        {subjects.loading ? <Loading /> : <div className="table-wrap"><table><thead><tr><th>Category</th><th>Fake</th><th>Real</th><th>Total</th><th /></tr></thead>
          <tbody>{subjects.data.items.map((s) => <tr key={s.subject}><td>{s.subject}</td><td>{s.Fake.toLocaleString()}</td><td>{s.Real.toLocaleString()}</td><td>{s.total.toLocaleString()}</td><td><Button variant="ghost" small onClick={() => setRename({ name: s.subject, to: s.subject })}>Rename</Button></td></tr>)}</tbody></table></div>}
      </div>
      {modal && <ArticleModal id={modal.id} edit={modal.edit} onClose={() => setModal(null)} onSaved={() => { setModal(null); toast('Article saved', 'ok'); reload(); subjects.reload() }} />}
      {rename && <Modal title={`Rename "${rename.name}"`} onClose={() => setRename(null)}><Field label="New category name" value={rename.to} onChange={(e) => setRename({ ...rename, to: e.target.value })} />
        <div className="row" style={{ justifyContent: 'flex-end' }}><Button variant="secondary" onClick={() => setRename(null)}>Cancel</Button><Button onClick={doRename} disabled={!rename.to.trim() || rename.to === rename.name}>Rename</Button></div></Modal>}
    </div>
  )
}

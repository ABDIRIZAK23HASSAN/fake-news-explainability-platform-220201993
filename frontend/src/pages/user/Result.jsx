import { useState } from 'react'
import { Link, NavLink, Outlet, useNavigate, useOutletContext, useParams } from 'react-router-dom'
import { api, download } from '../../api'
import { ChartBox, Evidence, ProbabilityMeter, useThemeColors, WordBars } from '../../components'
import { usePage } from '../../layout'
import { Alert, Button, Empty, fmtDate, LabelBadge, Loading, pct, useFetch, useToast } from '../../ui'

export function ResultLayout() {
  const { id } = useParams(); const toast = useToast(); const nav = useNavigate()
  const { data: r, error, loading } = useFetch(() => api.get(`/api/predictions/${id}`), [id])
  usePage([{ label: 'Dashboard', to: '/dashboard' }, { label: 'Prediction history', to: '/history' }, { label: r ? `Result #${r.prediction_id}` : 'Result' }])
  const [exporting, setExporting] = useState('')
  if (loading) return <Loading text="Loading the analysis..." />
  if (error) return <div className="stack"><Alert>{error}</Alert><Button variant="secondary" onClick={() => nav('/history')}>Back to history</Button></div>
  const fake = r.result === 'Fake'
  const exp = async (format) => { setExporting(format); try { await download(`/api/predictions/${id}/export`, { format }) } catch (e) { toast(e.message, 'error') } finally { setExporting('') } }
  const tab = (to, label, end) => <NavLink to={to} end={end} className={({ isActive }) => (isActive ? 'active' : '')}>{label}</NavLink>
  return (
    <div className="stack">
      <div className={`verdict ${fake ? 'fake' : 'real'}`}>
        <div className="row between">
          <div><div className="muted small">Prediction</div><div className="label">{fake ? 'Fake news' : 'Real news'}</div></div>
          <div className="right"><div className="label" style={{ fontSize: '1.7rem' }}>{pct(r.confidence, 2)}</div><div className="muted small">confidence</div></div>
        </div>
        <ProbabilityMeter fake={r.probabilities.Fake} real={r.probabilities.Real} />
        <p className="muted small" style={{ margin: '.6rem 0 0' }}>
          Processed in {r.processing_time.toFixed(2)} seconds on {fmtDate(r.date)}. Model: {r.model_info ? `${r.model_info.name}` : 'no longer available'}.
        </p>
      </div>
      {r.uncertain && <Alert kind="warn">The model is not very sure about this article (under 70% confidence). Treat this result with extra caution and verify it elsewhere.</Alert>}
      <div className="row between">
        <div><h2 style={{ margin: 0 }}>{r.title || 'Untitled article'}</h2></div>
        <div className="row"><Button variant="secondary" small loading={exporting === 'pdf'} onClick={() => exp('pdf')}>Export PDF</Button><Button variant="secondary" small loading={exporting === 'csv'} onClick={() => exp('csv')}>Export CSV</Button></div>
      </div>
      <nav className="tabs" aria-label="Result sections">
        {tab('', 'Overview', true)}{tab('explain', 'Explanation')}{tab('similar', `Similar news (${r.similar.length})`)}{tab('keywords', 'Keywords')}
      </nav>
      <Outlet context={r} />
    </div>
  )
}

export function ResultOverview() {
  const r = useOutletContext()
  const lime = r.explanation.lime
  return (
    <div className="split">
      <div className="panel">
        <h3>Your article, with the words that influenced the result</h3>
        {lime ? <Evidence segments={lime.highlight} predicted={r.result} /> : <p className="article">{r.text}</p>}
      </div>
      <div className="stack">
        <div className="panel"><h3>Strongest signals</h3>
          {lime ? <WordBars items={lime.feature_importance} predicted={r.result} limit={6} /> : <p className="muted">No explanation stored.</p>}
          <p className="small"><Link to="explain">See the full explanation</Link></p></div>
        <div className="panel"><h3>Top keywords</h3>
          {r.keywords.slice(0, 6).map((k) => <span className="kw" key={k.keyword}>{k.keyword}</span>)}
          <p className="small"><Link to="keywords">All keywords</Link></p></div>
        <Alert kind="warn">A statistical estimate, not a verdict on truth. Check important claims against trusted sources.</Alert>
      </div>
    </div>
  )
}

export function ResultExplain() {
  const r = useOutletContext()
  const methods = ['lime', 'shap'].filter((m) => r.explanation[m])
  const [m, setM] = useState(methods[0])
  const ex = r.explanation[m]
  if (!ex) return <Empty title="No explanation was stored for this prediction" />
  return (
    <div className="stack">
      <div className="row between">
        <p className="muted" style={{ margin: 0, maxWidth: 70 + 'ch' }}>
          A positive weight means the word supports the "{r.result}" prediction; a negative weight means it pushes against it.
          {m === 'lime' ? ' LIME tests how the prediction changes when words are removed from your text.' : ' SHAP splits the model output into a contribution per feature.'}
        </p>
        {methods.length > 1 && <div className="row" role="group" aria-label="Explanation method">
          {methods.map((x) => <Button key={x} small variant={x === m ? 'primary' : 'secondary'} onClick={() => setM(x)} aria-pressed={x === m}>{x.toUpperCase()}</Button>)}</div>}
      </div>
      <div className="grid g2">
        <div className="panel"><h3>Words supporting "{r.result}"</h3><WordBars items={ex.positive_words} predicted={r.result} limit={12} /></div>
        <div className="panel"><h3>Words pushing against it</h3><WordBars items={ex.negative_words} predicted={r.result} limit={12} /></div>
      </div>
      <div className="panel"><h3>Feature importance ranking</h3>
        <div className="table-wrap"><table><thead><tr><th>Rank</th><th>Word</th><th>Weight</th><th>Effect</th></tr></thead>
          <tbody>{ex.feature_importance.slice(0, 20).map((f, i) => <tr key={f.word}><td>{i + 1}</td><td>{f.word}</td><td>{f.weight > 0 ? '+' : ''}{f.weight.toFixed(4)}</td><td>{f.type === 'Positive' ? `Supports ${r.result}` : `Opposes ${r.result}`}</td></tr>)}</tbody></table></div></div>
      <div className="panel"><h3>Influential words inside the article</h3><Evidence segments={ex.highlight} predicted={r.result} /></div>
    </div>
  )
}

export function ResultSimilar() {
  const r = useOutletContext()
  if (!r.similar.length) return <Empty title="No similar articles found"><p>The reference dataset has no article close enough to this one.</p></Empty>
  return (
    <div className="panel">
      <p className="muted">The five reference articles most similar to yours (TF-IDF with cosine similarity). Their labels come from the dataset, not from this model.</p>
      <div className="table-wrap"><table>
        <thead><tr><th>Title</th><th>Subject</th><th>Similarity</th><th>Dataset label</th><th>Published</th></tr></thead>
        <tbody>{r.similar.map((s) => (
          <tr key={s.news_id}><td><Link to={`/articles/${s.news_id}`}>{s.title}</Link></td><td>{s.subject}</td><td>{pct(s.similarity, 0)}</td><td><LabelBadge label={s.label} /></td><td className="nowrap">{s.publication_date || '-'}</td></tr>))}</tbody>
      </table></div>
    </div>
  )
}

export function ResultKeywords() {
  const r = useOutletContext(); const c = useThemeColors()
  const kws = r.keywords
  if (!kws.length) return <Empty title="No keywords were extracted" />
  const maxI = Math.max(...kws.map((k) => k.importance))
  return (
    <div className="grid g2">
      <div className="panel"><h3>Keyword cloud</h3>
        <div style={{ lineHeight: 2.1 }}>{kws.map((k) => <span key={k.keyword} style={{ display: 'inline-block', fontFamily: 'var(--serif)', fontSize: `${0.95 + (k.importance / maxI) * 1.25}rem`, marginRight: '.9rem', fontWeight: k.importance / maxI > 0.7 ? 700 : 500 }}>{k.keyword}</span>)}</div></div>
      <div className="panel"><h3>Keyword frequency</h3>
        <ChartBox type="bar" height={Math.max(180, kws.length * 28)} data={{ labels: kws.map((k) => k.keyword), datasets: [{ label: 'Occurrences', data: kws.map((k) => k.frequency || 0), backgroundColor: c.navy }] }}
          options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} /></div>
      <div className="panel" style={{ gridColumn: '1 / -1' }}><h3>Top keywords</h3>
        <div className="table-wrap"><table><thead><tr><th>Keyword</th><th>Importance</th><th>Occurrences</th></tr></thead>
          <tbody>{kws.map((k) => <tr key={k.keyword}><td>{k.keyword}</td><td>{k.importance.toFixed(3)}</td><td>{k.frequency ?? '-'}</td></tr>)}</tbody></table></div></div>
    </div>
  )
}

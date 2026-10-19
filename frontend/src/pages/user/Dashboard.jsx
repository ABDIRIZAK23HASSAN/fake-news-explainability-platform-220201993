import { Link, useNavigate } from 'react-router-dom'
import { api } from '../../api'
import { usePage } from '../../layout'
import { Alert, Empty, fmtDate, LabelBadge, Loading, pct, StatCard, useFetch } from '../../ui'

export default function Dashboard() {
  usePage([{ label: 'Dashboard' }])
  const nav = useNavigate()
  const { data, error, loading } = useFetch(() => api.get('/api/users/dashboard'))
  if (loading) return <Loading />
  if (error) return <Alert>{error}</Alert>
  return (
    <div className="stack">
      <div className="row between"><h1>{data.welcome}</h1>
        <div className="row"><Link className="btn" to="/analyze">Analyze an article</Link><Link className="btn secondary" to="/history">Open history</Link></div></div>
      <div className="grid g4">
        <StatCard value={data.total_predictions} label="Total predictions" />
        <StatCard value={data.fake_detected} label="Fake news detected" tone="fake" />
        <StatCard value={data.real_detected} label="Real news detected" tone="real" />
        <StatCard value={pct(data.average_confidence)} label="Average confidence" />
      </div>
      <div className="panel">
        <h2>Recent predictions</h2>
        {!data.recent_predictions.length ? <Empty title="No analyses yet"><p>Paste an article or upload a document to get your first result.</p><Link className="btn" to="/analyze">Analyze an article</Link></Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>Article</th><th>Result</th><th>Confidence</th><th>Date</th></tr></thead>
            <tbody>{data.recent_predictions.map((p) => (
              <tr key={p.prediction_id} style={{ cursor: 'pointer' }} onClick={() => nav(`/results/${p.prediction_id}`)}>
                <td><Link to={`/results/${p.prediction_id}`} onClick={(e) => e.stopPropagation()}>{p.title || `${p.snippet.slice(0, 70)}...`}</Link></td>
                <td><LabelBadge label={p.result} /></td><td>{pct(p.confidence)}</td><td className="nowrap">{fmtDate(p.date)}</td>
              </tr>))}</tbody>
          </table></div>)}
      </div>
      <div className="grid g2">
        <div className="panel"><h3>Recent uploaded news</h3>
          {data.recent_uploaded_news.length ? data.recent_uploaded_news.map((p) => <p key={p.prediction_id}><Link to={`/results/${p.prediction_id}`}>{p.title}</Link> <span className="muted small">{fmtDate(p.date)}</span></p>) : <p className="muted">Documents you upload will appear here.</p>}</div>
        <div className="panel"><h3>Recently analyzed articles</h3>
          {data.recently_analyzed_articles.length ? data.recently_analyzed_articles.map((p) => <p key={p.prediction_id}><Link to={`/results/${p.prediction_id}`}>{p.title.slice(0, 60)}</Link> <LabelBadge label={p.result} /></p>) : <p className="muted">Nothing analyzed yet.</p>}</div>
      </div>
    </div>
  )
}

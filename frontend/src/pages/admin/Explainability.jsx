import { api } from '../../api'
import { usePage } from '../../layout'
import { Alert, Empty, Loading, useFetch } from '../../ui'

const Table = ({ rows, empty }) => !rows.length ? <p className="muted small">{empty}</p> : (
  <div className="table-wrap"><table><thead><tr><th>Word</th><th>Occurrences</th><th>Average weight</th><th>Total weight</th></tr></thead>
    <tbody>{rows.map((r, i) => <tr key={`${r.word}${r.method}${i}`}><td>{r.word} <span className="muted small">{r.method}</span></td><td>{r.occurrences}</td><td>{r.avg_contribution.toFixed(4)}</td><td>{r.total_weight.toFixed(3)}</td></tr>)}</tbody></table></div>)

export default function Explainability() {
  usePage([{ label: 'Administration', to: '/admin' }, { label: 'Explainability' }])
  const { data: d, error, loading } = useFetch(() => api.get('/api/admin/explainability'))
  if (loading) return <Loading />
  if (error) return <Alert>{error}</Alert>
  if (!d.most_influential_words.length) return <div className="stack"><h1>Explainability monitoring</h1><Empty title="Nothing to monitor yet"><p>Explanations are collected as users analyze articles.</p></Empty></div>
  return (
    <div className="stack">
      <h1>Explainability monitoring</h1>
      <p className="muted" style={{ maxWidth: '70ch' }}>The words that most often push the model towards each verdict across all users. If a word that has nothing to do with truthfulness (a publisher name, a location) ranks high, the model may be relying on a shortcut in the data, which is a sign of bias.</p>
      <div className="grid g2">
        <div className="panel"><h3>Most common fake news indicators</h3><Table rows={d.fake_indicators} empty="No fake predictions yet." /></div>
        <div className="panel"><h3>Most common real news indicators</h3><Table rows={d.real_indicators} empty="No real predictions yet." /></div>
        <div className="panel"><h3>Most influential words overall</h3><div className="table-wrap"><table><thead><tr><th>Word</th><th>Total weight</th></tr></thead><tbody>{d.most_influential_words.map((w) => <tr key={w.word}><td>{w.word}</td><td>{w.total_weight}</td></tr>)}</tbody></table></div></div>
        <div className="panel"><h3>Average SHAP values</h3><Table rows={d.average_shap_values} empty="SHAP values are stored when the active model is Logistic Regression or XGBoost." /></div>
      </div>
    </div>
  )
}

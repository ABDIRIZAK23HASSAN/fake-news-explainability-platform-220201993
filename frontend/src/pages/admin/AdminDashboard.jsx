import { api, download } from '../../api'
import { ChartBox, useThemeColors } from '../../components'
import { usePage } from '../../layout'
import { Alert, Button, Loading, pct, StatCard, useFetch, useToast } from '../../ui'

export default function AdminDashboard() {
  usePage([{ label: 'Administration' }, { label: 'Dashboard' }])
  const c = useThemeColors(); const toast = useToast()
  const { data: d, error, loading } = useFetch(() => api.get('/api/admin/analytics'))
  if (loading) return <Loading />
  if (error) return <Alert>{error}</Alert>
  const exp = (format) => download('/api/admin/reports/analytics', { format }).catch((e) => toast(e.message, 'error'))
  const m = d.active_model
  return (
    <div className="stack">
      <div className="row between"><h1>Administrator dashboard</h1>
        <div className="row"><Button variant="secondary" small onClick={() => exp('pdf')}>Export report (PDF)</Button><Button variant="secondary" small onClick={() => exp('csv')}>Export report (CSV)</Button></div></div>
      {!m && <Alert kind="warn">No model is active, so users cannot analyze articles. Train and activate one in Models.</Alert>}
      <div className="grid g4">
        <StatCard value={d.total_users} label="Total users" />
        <StatCard value={d.active_users} label={`Active users (logged in within ${d.active_users_window_days} days)`} />
        <StatCard value={d.total_predictions} label="Total predictions" />
        <StatCard value={d.total_news_articles.toLocaleString()} label="News articles in dataset" />
        <StatCard value={d.fake_predictions} label="Fake predictions" tone="fake" />
        <StatCard value={d.real_predictions} label="Real predictions" tone="real" />
        <StatCard value={m ? m.algorithm.replace('_', ' ') : 'None'} label={m ? `Active model, F1 ${pct(m.f1)}` : 'Active model'} />
        <StatCard value={`${pct(d.average_confidence, 0)}`} label={`Average confidence, ${d.average_processing_time ? d.average_processing_time.toFixed(2) + 's' : '-'} per analysis`} />
      </div>
      <div className="grid g2">
        <div className="panel"><h3>Daily predictions (last 30 days)</h3>
          <ChartBox type="bar" empty="No predictions in the last 30 days." data={{ labels: d.daily_predictions.map((x) => x.date.slice(5)), datasets: [
            { label: 'Fake', data: d.daily_predictions.map((x) => x.Fake), backgroundColor: c.fake }, { label: 'Real', data: d.daily_predictions.map((x) => x.Real), backgroundColor: c.real }] }}
            options={{ scales: { x: { stacked: true }, y: { stacked: true } } }} /></div>
        <div className="panel"><h3>Monthly prediction trend</h3>
          <ChartBox type="line" empty="No monthly data yet." data={{ labels: d.monthly_predictions.map((x) => x.month), datasets: [
            { label: 'Fake', data: d.monthly_predictions.map((x) => x.Fake), borderColor: c.fake, backgroundColor: c.fake, tension: .3 }, { label: 'Real', data: d.monthly_predictions.map((x) => x.Real), borderColor: c.real, backgroundColor: c.real, tension: .3 }] }} /></div>
        <div className="panel"><h3>Fake vs real predictions</h3>
          <ChartBox type="doughnut" empty="No predictions yet." data={{ labels: ['Fake', 'Real'], datasets: [{ data: d.total_predictions ? [d.fake_predictions, d.real_predictions] : [], backgroundColor: [c.fake, c.real], borderWidth: 0 }] }} /></div>
        <div className="panel"><h3>Model performance comparison</h3>
          <ChartBox type="bar" empty="No trained models yet." data={{ labels: d.model_comparison.map((x) => x.algorithm.replace('_', ' ')), datasets: ['accuracy', 'precision', 'recall', 'f1'].map((k, i) => ({ label: k, data: d.model_comparison.map((x) => x[k]), backgroundColor: [c.navy, c.soft, c.real, c.fake][i] })) }}
            options={{ scales: { y: { min: 0.9, max: 1 } } }} /></div>
      </div>
    </div>
  )
}

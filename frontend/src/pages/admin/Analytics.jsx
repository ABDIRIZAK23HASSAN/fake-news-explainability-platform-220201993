import { api, download } from '../../api'
import { ChartBox, useThemeColors } from '../../components'
import { usePage } from '../../layout'
import { Alert, Button, Loading, useFetch, useToast } from '../../ui'

export default function Analytics() {
  usePage([{ label: 'Administration', to: '/admin' }, { label: 'Analytics' }])
  const c = useThemeColors(); const toast = useToast()
  const { data: d, error, loading } = useFetch(() => api.get('/api/admin/analytics'))
  if (loading) return <Loading />
  if (error) return <Alert>{error}</Alert>
  const k = d.content
  const exp = (format) => download('/api/admin/reports/analytics', { format }).catch((e) => toast(e.message, 'error'))
  const ds = d.dataset_size
  return (
    <div className="stack">
      <div className="row between"><h1>Analytics</h1><div className="row"><Button variant="secondary" small onClick={() => exp('pdf')}>Export PDF</Button><Button variant="secondary" small onClick={() => exp('csv')}>Export CSV</Button></div></div>
      <div className="grid g2">
        <div className="panel"><h3>Prediction trend over time</h3>
          <ChartBox type="line" empty="No predictions yet." data={{ labels: d.daily_predictions.map((x) => x.date.slice(5)), datasets: [{ label: 'Predictions per day', data: d.daily_predictions.map((x) => x.Fake + x.Real), borderColor: c.navy, backgroundColor: c.navy, tension: .3 }] }} /></div>
        <div className="panel"><h3>Dataset distribution</h3>
          <ChartBox type="doughnut" data={{ labels: ['Fake', 'Real'], datasets: [{ data: ds.total ? [ds.fake || 0, ds.real || 0] : [], backgroundColor: [c.fake, c.real], borderWidth: 0 }] }} /></div>
        <div className="panel"><h3>Most frequent keywords in analyses</h3>
          <ChartBox type="bar" empty="Keywords appear after users analyze articles." height={Math.max(200, k.frequent_keywords.length * 24)} data={{ labels: k.frequent_keywords.map((x) => x.keyword), datasets: [{ label: 'Analyses containing it', data: k.frequent_keywords.map((x) => x.count), backgroundColor: c.navy }] }} options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} /></div>
        <div className="panel"><h3>Fake articles by topic (dataset)</h3>
          <ChartBox type="bar" data={{ labels: k.fake_news_topics.map((x) => x.subject), datasets: [{ label: 'Fake articles', data: k.fake_news_topics.map((x) => x.count), backgroundColor: c.fake }] }} options={{ plugins: { legend: { display: false } } }} /></div>
        <div className="panel"><h3>Model comparison</h3>
          <ChartBox type="bar" empty="No trained models yet." data={{ labels: d.model_comparison.map((x) => x.algorithm.replace('_', ' ')), datasets: [{ label: 'F1-score', data: d.model_comparison.map((x) => x.f1), backgroundColor: c.navy }, { label: 'Accuracy', data: d.model_comparison.map((x) => x.accuracy), backgroundColor: c.real }] }} options={{ scales: { y: { min: 0.9, max: 1 } } }} /></div>
        <div className="panel"><h3>Processing time distribution</h3>
          <ChartBox type="bar" data={{ labels: d.processing_time_distribution.map((x) => x.bucket), datasets: [{ label: 'Analyses', data: d.processing_time_distribution.map((x) => x.count), backgroundColor: c.navy }] }} options={{ plugins: { legend: { display: false } } }} /></div>
        <div className="panel"><h3>News subjects in the dataset</h3>
          <ChartBox type="bar" data={{ labels: k.news_subjects.map((x) => x.subject), datasets: [{ label: 'Articles', data: k.news_subjects.map((x) => x.count), backgroundColor: c.soft }] }} options={{ plugins: { legend: { display: false } } }} /></div>
        <div className="panel"><h3>User activity (top users)</h3>
          <ChartBox type="bar" empty="No user activity yet." data={{ labels: d.user_activity.map((x) => x.email), datasets: [{ label: 'Predictions', data: d.user_activity.map((x) => x.predictions), backgroundColor: c.navy }] }} options={{ indexAxis: 'y', plugins: { legend: { display: false } } }} /></div>
      </div>
    </div>
  )
}

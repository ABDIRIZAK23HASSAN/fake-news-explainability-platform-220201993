import { useParams } from 'react-router-dom'
import { api } from '../../api'
import { usePage } from '../../layout'
import { Alert, LabelBadge, Loading, useFetch } from '../../ui'

export default function ArticleView() {
  const { newsId } = useParams()
  const { data: a, error, loading } = useFetch(() => api.get(`/api/news/articles/${newsId}`), [newsId])
  usePage([{ label: 'Dashboard', to: '/dashboard' }, { label: 'Reference article' }])
  if (loading) return <Loading />
  if (error) return <Alert>{error}</Alert>
  return (
    <div className="panel stack" style={{ maxWidth: 860 }}>
      <div className="row"><LabelBadge label={a.label} /><span className="muted small">{a.subject}{a.publication_date ? `, ${a.publication_date}` : ''}</span></div>
      <h1>{a.title}</h1>
      <p className="muted small">This is an article from the reference dataset. Its label comes from the dataset's authors.</p>
      <div className="article">{a.content}</div>
    </div>
  )
}

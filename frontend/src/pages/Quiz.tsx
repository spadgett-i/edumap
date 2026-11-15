import { useEffect, useState } from 'react'
import { api } from '../api'
import { Icon } from '../components/Icon'
import { QuizModule } from '../components/QuizModule'
import { Shell } from '../components/Shell'
import { navigate, paths } from '../lib/router'

export function QuizPage({ projectId }: { projectId: string }) {
  const [title, setTitle] = useState('')
  useEffect(() => { api.getMap(projectId).then((m) => setTitle(m.title)).catch(() => setTitle('')) }, [projectId])

  return (
    <Shell active="library" title={title ? `Cuestionario · ${title}` : 'Cuestionario'}
      actions={<a className="btn btn--secondary" href={paths.editor(projectId)}><Icon name="back" /> Mapa conceptual</a>}>
      <QuizModule projectId={projectId} onBackToMap={() => navigate(paths.editor(projectId))} />
    </Shell>
  )
}

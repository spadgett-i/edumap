import { useRoute } from './lib/router'
import { EditorPage } from './pages/Editor'
import { HomePage } from './pages/Home'
import { LibraryPage } from './pages/Library'
import { ProcessingPage } from './pages/Processing'
import { QuizPage } from './pages/Quiz'
import { UploadPage } from './pages/Upload'

export default function App() {
  const route = useRoute()
  switch (route.name) {
    case 'upload': return <UploadPage />
    case 'processing': return <ProcessingPage key={route.id} id={route.id} />
    case 'library': return <LibraryPage />
    case 'editor': return <EditorPage key={route.id} projectId={route.id} />
    case 'quiz': return <QuizPage key={route.id} projectId={route.id} />
    default: return <HomePage />
  }
}

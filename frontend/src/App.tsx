import { Routes, Route } from 'react-router-dom'
import { useWebSocket } from './hooks/useWebSocket'
import Layout from './components/Layout'
import CreatePage from './pages/CreatePage'
import QueuePage from './pages/QueuePage'
import GalleryPage from './pages/GalleryPage'
import ModelsPage from './pages/ModelsPage'
import SettingsPage from './pages/SettingsPage'

export default function App() {
  useWebSocket()
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<CreatePage />} />
        <Route path="/queue" element={<QueuePage />} />
        <Route path="/gallery" element={<GalleryPage />} />
        <Route path="/models" element={<ModelsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </Layout>
  )
}

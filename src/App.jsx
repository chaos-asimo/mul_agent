import { Routes, Route } from 'react-router-dom'
import Login from './pages/Login'
import Layout from './components/Layout'
import LobsterClaw from './pages/LobsterClaw'
import ScriptManager from './pages/ScriptManager'
import AIChat from './pages/AIChat'
import ModelManager from './pages/ModelManager'
import AgentManager from './pages/AgentManager'
import MemoryManager from './pages/MemoryManager'
import AttachmentManager from './pages/AttachmentManager'
import { useAuthStore } from './stores/authStore'
import { Navigate } from 'react-router-dom'

function ProtectedRoute({ children }) {
  const { user, loading } = useAuthStore()
  
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="loading-pulse text-gray-500">加载中...</div>
      </div>
    )
  }
  
  if (!user) {
    return <Navigate to="/login" replace />
  }
  
  return children
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={
        <ProtectedRoute>
          <Layout />
        </ProtectedRoute>
      }>
        <Route index element={<LobsterClaw />} />
        <Route path="lobster-claw" element={<LobsterClaw />} />
        <Route path="scripts" element={<ScriptManager />} />
        <Route path="ai-chat" element={<AIChat />} />
        <Route path="models" element={<ModelManager />} />
        <Route path="agents" element={<AgentManager />} />
        <Route path="memory" element={<MemoryManager />} />
        <Route path="attachments" element={<AttachmentManager />} />
      </Route>
    </Routes>
  )
}

export default App

import { StrictMode, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { marked } from 'marked'
import './index.css'
import App from './App.jsx'
import { useAuthStore } from './stores/authStore'

// marked GFM 会把单个 ~text~ 也解析为 <del>，但标准 GFM 只认 ~~text~~。
// 全局 walkTokens 把单波浪号的 del 还原为普通文本，避免 "1~10"、"a~b" 被误渲染。
marked.use({
  walkTokens(token) {
    if (token.type === 'del' && token.raw && !token.raw.startsWith('~~')) {
      token.type = 'text'
      token.text = token.raw
      delete token.tokens
    }
  },
})

function AppWrapper() {
  const { checkAuth } = useAuthStore()
  
  useEffect(() => {
    checkAuth()
  }, [checkAuth])
  
  return <App />
}

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter basename="/v2">
      <AppWrapper />
    </BrowserRouter>
  </StrictMode>,
)

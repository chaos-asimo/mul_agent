import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

// 入口前缀由后端注入 window.__BASE__（"/v3" 或 "/clow"），
// 使 /clow 和 /v3 两个入口完全等价。fallback 到 "/v3"。
const base = (typeof window !== 'undefined' && window.__BASE__) || '/v3'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter basename={base}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)

import { useAuthStore } from '../stores/authStore'

export const API_BASE = '/api/lobster-mu'

// 入口前缀由后端注入 window.__BASE__（"/v3" 或 "/clow"），
// 401 跳转登录页时用它拼接，避免硬编码导致 /clow 入口跳错。
const BASE = (typeof window !== 'undefined' && window.__BASE__) || '/v3'

/**
 * 401/403 时清除本地登录态并跳转到 {BASE}/login（已在登录页则只清状态）
 */
function handleUnauthorized() {
  useAuthStore.getState().clearUser()
  const loginPath = `${BASE}/login`
  if (!window.location.pathname.startsWith(loginPath)) {
    window.location.replace(loginPath)
  }
}

async function request(path, options = {}) {
  const url = `${API_BASE}${path}`
  const method = (options.method || 'GET').toUpperCase()
  // GET/DELETE 幂等：遇到网络层重置（ERR_CONNECTION_RESET 等）自动重试一次，
  // 用新连接规避部分浏览器/代理对 keep-alive 连接的 RST。
  const retryable = method === 'GET' || method === 'DELETE'
  const attempt = async () => {
    const response = await fetch(url, { credentials: 'include', ...options })
    if (response.status === 401 || response.status === 403) {
      let detail = ''
      try {
        const body = await response.json()
        detail = body.detail || body.error || body.message || ''
      } catch (e) {
        /* 忽略 */
      }
      handleUnauthorized()
      const error = new Error(detail || '未登录或登录已过期')
      error.status = response.status
      throw error
    }
    return response
  }
  try {
    return await attempt()
  } catch (e) {
    // 幂等方法遇到网络层重置（ERR_CONNECTION_RESET 等）时重试：
    // 先用原方法重试一次；若仍为网络错误，则改用 POST + X-HTTP-Method-Override
    // 隧道化（部分浏览器/代理会直接重置 DELETE 连接）。
    if (retryable && e instanceof TypeError && !e.status) {
      try {
        return await attempt()
      } catch (e2) {
        if (e2 instanceof TypeError && !e2.status && (method === 'DELETE' || method === 'PUT')) {
          const overrideOptions = {
            ...options,
            method: 'POST',
            headers: { ...(options.headers || {}), 'X-HTTP-Method-Override': method },
          }
          const overrideAttempt = async () => {
            const response = await fetch(url, { credentials: 'include', ...overrideOptions })
            if (response.status === 401 || response.status === 403) {
              handleUnauthorized()
              const err = new Error('未登录或登录已过期')
              err.status = response.status
              throw err
            }
            return response
          }
          return await overrideAttempt()
        }
        throw e2
      }
    }
    throw e
  }
}

export async function apiGet(path) {
  const response = await request(path)
  return response.json()
}

export async function apiPost(path, body) {
  const response = await request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  return response.json()
}

export async function apiPut(path, body) {
  const response = await request(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return response.json()
}

export async function apiDelete(path) {
  const response = await request(path, { method: 'DELETE' })
  return response.json()
}

export async function apiUpload(path, formData) {
  const response = await request(path, { method: 'POST', body: formData })
  return response.json()
}

/**
 * SSE 流式聊天：返回原始 Response，由调用方读取 body 流
 * 支持 signal（AbortSignal）用于前端主动中断流式请求
 */
export async function apiStream(path, body, signal) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })
}

/**
 * 读取文件内容：文本类直接 FileReader 读取；pdf/doc/xls(x)/ppt(x) 走 /upload/text 解析
 * 分类逻辑与 v2 LobsterClaw.jsx 保持一致，单文件不超过 10MB（由调用方校验）
 */
export async function readFileContent(file) {
  const ext = file.name.split('.').pop().toLowerCase()

  if (['txt', 'md', 'json', 'py', 'js', 'html', 'css', 'xml', 'csv'].includes(ext)) {
    return new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = (e) => resolve(e.target.result)
      reader.onerror = () => resolve('')
      reader.readAsText(file, 'utf-8')
    })
  }

  if (['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'].includes(ext)) {
    try {
      const formData = new FormData()
      formData.append('file', file)
      const result = await apiUpload('/upload/text', formData)
      return result.success && result.content ? result.content : ''
    } catch (error) {
      console.error('上传文件解析失败:', error)
      return ''
    }
  }

  return ''
}

export function formatSize(size) {
  if (size == null) return ''
  if (size > 1024 * 1024) return (size / 1024 / 1024).toFixed(2) + ' MB'
  if (size > 1024) return (size / 1024).toFixed(1) + ' KB'
  return size + ' B'
}

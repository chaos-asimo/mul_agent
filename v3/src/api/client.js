import { useAuthStore } from '../stores/authStore'

export const API_BASE = '/api/lobster-mu'

/**
 * 401/403 时清除本地登录态并跳转 /v3/login（已在登录页则只清状态）
 */
function handleUnauthorized() {
  useAuthStore.getState().clearUser()
  if (!window.location.pathname.startsWith('/v3/login')) {
    window.location.replace('/v3/login')
  }
}

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    ...options,
  })
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
 */
export async function apiStream(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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

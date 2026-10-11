import { useMemo } from 'react'
import { marked } from 'marked'
import { highlightPythonCode, escapeHtml } from '../utils/highlight'

marked.setOptions({ gfm: true, breaks: true })

// 自定义代码块渲染：Python（含未指定语言）代码块做关键字高亮，与 v1 能力一致
const renderer = new marked.Renderer()
renderer.code = ({ text, lang }) => {
  const language = (lang || '').toLowerCase()
  const isPy = !language || language === 'python' || language === 'py'
  const inner = isPy ? highlightPythonCode(text) : escapeHtml(text)
  const cls = isPy ? 'python-highlight' : ''
  return `<pre><code${cls ? ` class="${cls}"` : ''}>${inner}</code></pre>`
}
marked.use({ renderer })

// 去掉 URL 末尾误并入的标点（中英文括号/句号/逗号/分号/感叹问号等，含其百分号编码）
const TRAIL_PUNCT = /(?:[。．.，,；;！!？?）)】」』]|%E3%80%82|%EF%BC%8E|%EF%BC%8C|%EF%BC%9B|%EF%BC%81|%EF%BC%9F|%EF%BC%89|%29|%2C|%3B|%21|%3F|%5D)+$/i
function cleanUrl(u) {
  let cur = String(u || '')
  let prev
  do { prev = cur; cur = cur.replace(TRAIL_PUNCT, '') } while (cur !== prev)
  return cur
}

// 桌面浏览器用新标签页打开链接；移动端/WebView 下在当前窗口导航，
// 使其进入 WebView 历史栈，系统返回键可回到原页面（target=_blank 会脱离返回栈）。
const OPEN_IN_NEW_TAB = typeof navigator !== 'undefined'
  && !/Android|iPhone|iPad|iPod|Mobile|HarmonyOS|WebView|MicroMessenger|wxwork/i.test(navigator.userAgent || '')

// 给所有 <a> 注入链接属性，并清洗 href 尾部标点（不改文本，保证显示与跳转一致）
function sanitizeAnchors(html) {
  const targetAttr = OPEN_IN_NEW_TAB
    ? ' target="_blank" rel="noopener noreferrer"'
    : ' target="_self"'
  return String(html).replace(/<a\b([^>]*?)\shref="([^"]*)"/gi, (m, attrs, url) => {
    const clean = cleanUrl(url)
    return `<a${targetAttr}${attrs} href="${clean}"`
  })
}

function MarkdownContent({ content }) {
  const html = useMemo(() => {
    try {
      return sanitizeAnchors(marked.parse(content || ''))
    } catch {
      return content || ''
    }
  }, [content])
  return <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} />
}

export default MarkdownContent

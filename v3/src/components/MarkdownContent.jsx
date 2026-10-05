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

function MarkdownContent({ content }) {
  const html = useMemo(() => {
    try {
      return marked.parse(content || '')
    } catch {
      return content || ''
    }
  }, [content])
  return <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} />
}

export default MarkdownContent

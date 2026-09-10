import { useMemo } from 'react'
import { marked } from 'marked'

marked.setOptions({ gfm: true, breaks: true })

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

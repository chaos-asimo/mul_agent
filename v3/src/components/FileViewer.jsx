import { useEffect, useState, useMemo, useCallback } from 'react'
import { Download, Loader2, FileWarning } from 'lucide-react'
import { apiGet, API_BASE } from '../api/client'
import {
  highlightCode, langFromFilename,
  isTextFile, isPdfFile, isOfficeFile, isImageFile,
} from '../utils/highlight'
import MarkdownContent from './MarkdownContent'
import Modal from './Modal'
import OfficePreview from './OfficePreview'

// 可在浏览器原生渲染的现代 Office 格式
const NATIVE_OFFICE = /\.(docx|xlsx?|pptx)$/i

/**
 * 文件内容查看器（通用，「我的文件」与「脚本产物」共用）：
 * - 入参可传 file={{id, filename}}，或显式 filename/rawUrl/downloadUrl/contentUrl
 * - markdown → Markdown 渲染；文本/代码 → 语法高亮
 * - pdf → 浏览器原生内嵌预览；office(docx/xlsx/pptx) → 前端原生渲染
 * - 旧版 .doc/.ppt → 提取文本（需 contentUrl）；其它 → 下载
 */
export default function FileViewer({ file, filename, rawUrl, downloadUrl, contentUrl, onClose, textOnly = false }) {
  const name = file?.filename || filename || ''
  const baseRaw = rawUrl || (file ? `${API_BASE}/files/${file.id}/raw` : '')
  const baseDownload = downloadUrl || (baseRaw ? `${baseRaw}?download=1` : '')
  const baseContent = contentUrl || (file ? `/files/${file.id}` : '')

  const [content, setContent] = useState('')
  const [contentSize, setContentSize] = useState(0)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    setError('')
    setContent('')
    // office-native / pdf / image 不需要文本内容
    const kind = pickKind(name)
    if (!textOnly && (kind === 'pdf' || kind === 'office-native' || kind === 'image' || kind === 'other')) {
      setLoading(false)
      return
    }
    const load = async () => {
      try {
        if (baseContent) {
          const res = await apiGet(baseContent)
          if (!alive) return
          if (res.success && res.file) {
            setContent(res.file.content || '')
            setContentSize(res.file.size || 0)
          } else if (kind === 'office-text') {
            // 无提取文本，走回退提示
            setError('__no_text__')
          } else {
            setError(res.error || '读取失败')
          }
        } else if (baseRaw) {
          // 无内容接口时，直接取原始文本（适用于脚本产物中的文本类文件）
          const res = await fetch(baseRaw, { credentials: 'include' })
          if (!alive) return
          if (!res.ok) throw new Error(`加载失败 (${res.status})`)
          const text = await res.text()
          setContent(text)
        } else if (kind === 'office-text') {
          setError('__no_text__')
        } else {
          setError('读取失败')
        }
      } catch (e) {
        if (alive) setError(kind === 'office-text' ? '__no_text__' : (e?.message || '读取失败'))
      } finally {
        if (alive) setLoading(false)
      }
    }
    load()
    return () => { alive = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [name, baseRaw, baseContent, textOnly])

  const getBuffer = useCallback(async () => {
    const res = await fetch(baseRaw, { credentials: 'include' })
    if (!res.ok) throw new Error(`加载失败 (${res.status})`)
    return await res.arrayBuffer()
  }, [baseRaw])

  const kind = useMemo(() => pickKind(name), [name])

  const body = () => {
    if (loading) {
      return (
        <div className="flex items-center justify-center h-full text-xs t-text-faint gap-2">
          <Loader2 className="w-4 h-4 animate-spin" /> 加载中...
        </div>
      )
    }
    if (textOnly && (kind === 'office-native' || kind === 'office-text' || kind === 'pdf' || kind === 'other')) {
      return (
        <div className="overflow-y-auto flex-1 min-h-0 pr-1 space-y-3">
          <p className="text-[11px] t-text-faint flex items-center gap-1">
            <FileWarning className="w-3 h-3" /> 知识库仅保留提取文本，以下为文档内容（复用统一排版渲染）。
          </p>
          <div className="file-viewer-text t-bg-card border t-border rounded-lg p-4">{content || '（未提取到文本内容）'}</div>
        </div>
      )
    }
    if (kind === 'markdown') {
      return <div className="overflow-y-auto flex-1 min-h-0 pr-1"><MarkdownContent content={content} /></div>
    }
    if (kind === 'code') {
      const lang = langFromFilename(name)
      const html = highlightCode(content, lang)
      return (
        <pre className="code-view overflow-auto flex-1 min-h-0 p-3 t-bg-card border t-border rounded-lg"
          dangerouslySetInnerHTML={{ __html: html }} />
      )
    }
    if (kind === 'pdf') {
      return <iframe title={name} src={baseRaw} className="file-viewer-frame" />
    }
    if (kind === 'image') {
      return (
        <div className="flex-1 min-h-0 flex items-center justify-center overflow-auto">
          <img
            src={baseRaw}
            alt={name}
            className="max-w-full max-h-full object-contain rounded-lg"
          />
        </div>
      )
    }
    if (kind === 'office-native') {
      if (error && error !== '__no_text__') {
        return (
          <div className="flex flex-col items-center justify-center h-full text-xs t-text-faint gap-2">
            <FileWarning className="w-6 h-6" /> {error}
          </div>
        )
      }
      return <OfficePreview filename={name} getBuffer={getBuffer} />
    }
    if (kind === 'office-text') {
      return (
        <div className="overflow-y-auto flex-1 min-h-0 pr-1 space-y-3">
          <p className="text-[11px] t-text-faint flex items-center gap-1">
            <FileWarning className="w-3 h-3" /> 旧版二进制格式（.doc/.ppt）浏览器无法原生渲染，以下为提取文本；需原始排版请点「下载原文件」。
          </p>
          <div className="file-viewer-text t-bg-card border t-border rounded-lg p-4">{content || '（未提取到文本内容）'}</div>
        </div>
      )
    }
    // other
    return (
      <div className="flex flex-col items-center justify-center h-full text-xs t-text-faint gap-3">
        <FileWarning className="w-6 h-6" />
        该类型暂不支持在线预览，请下载后查看。
        <a href={baseDownload} className="t-text-accent underline">下载原文件</a>
      </div>
    )
  }

  return (
    <Modal title={`查看文件：${name}`} onClose={onClose} max>
      <div className="flex items-center justify-between mb-3 shrink-0">
        <span className="text-[11px] t-text-faint">
          {contentSize ? `${(contentSize / 1024).toFixed(1)} KB` : ''}
        </span>
        <a href={baseDownload}
          className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg border t-border-strong t-text-2 t-hover-card">
          <Download className="w-3 h-3" /> 下载原文件
        </a>
      </div>
      <div className="flex-1 min-h-0 flex flex-col">{body()}</div>
    </Modal>
  )
}

function pickKind(name) {
  if (/\.md|markdown$/i.test(name)) return 'markdown'
  if (isPdfFile(name)) return 'pdf'
  if (isImageFile(name)) return 'image'
  if (NATIVE_OFFICE.test(name)) return 'office-native'
  if (isOfficeFile(name)) return 'office-text'
  if (isTextFile(name)) return 'code'
  return 'other'
}

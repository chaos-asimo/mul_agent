import { useState } from 'react'
import { Paperclip, FileText, X, UploadCloud, Trash2, PlusCircle, RefreshCw, Eye } from 'lucide-react'
import { apiUpload, apiGet, apiDelete, formatSize } from '../api/client'
import FileViewer from './FileViewer'

const SUPPORTED_TEXT = 'txt / md / json / py / js / html / css / xml / csv'
const SUPPORTED_BINARY = 'pdf / doc(x) / xls(x) / ppt(x)'

function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ''
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function FilesTab({
  pendingFiles, onAddFiles, onRemoveFile,
  files, onFilesChange, uploading, setUploading,
}) {
  const [error, setError] = useState('')
  const [viewing, setViewing] = useState(null) // 正在查看的文件 {id, filename}

  // 上传到「我的文件」库（持久化），成功后将其加入待发送以便直接复用
  const handleUpload = async (fileList) => {
    if (!fileList?.length) return
    setError('')
    setUploading(true)
    try {
      const fd = new FormData()
      for (const f of fileList) fd.append('files', f)
      const res = await apiUpload('/upload', fd)
      const ok = (res.results || []).filter((r) => r.success)
      const failed = (res.results || []).filter((r) => !r.success)
      if (failed.length) setError(failed.map((f) => `${f.filename}: ${f.error || '失败'}`).join('；'))
      // 把新上传的文件加入待发送（取完整内容），实现「上传即可用」
      for (const r of ok) {
        try {
          const detail = await apiGet(`/files/${r.file_id}`)
          if (detail.success && detail.file) {
            onAddFiles([{ filename: detail.file.filename, content: detail.file.content, size: detail.file.size }])
          }
        } catch (e) { /* 列表仍会刷新，内容不阻塞 */ }
      }
      onFilesChange()
    } catch (e) {
      setError('上传失败：' + (e?.message || '未知错误'))
    } finally {
      setUploading(false)
    }
  }

  // 从文件库复用：取完整内容加入待发送
  const reuse = async (file) => {
    try {
      const detail = await apiGet(`/files/${file.id}`)
      if (detail.success && detail.file) {
        onAddFiles([{ filename: detail.file.filename, content: detail.file.content, size: detail.file.size }])
      }
    } catch (e) {
      setError('加入会话失败：' + (e?.message || '未知错误'))
    }
  }

  const remove = async (file) => {
    if (!confirm(`删除文件「${file.filename}」？`)) return
    try {
      await apiDelete(`/files/${file.id}`)
      onFilesChange()
    } catch (e) {
      setError('删除失败：' + (e?.message || '未知错误'))
    }
  }

  return (
    <div className="space-y-5">
      {/* 待发送（随下一条消息发送） */}
      <div>
        <h3 className="text-sm font-semibold t-text-2 mb-1">待发送文件</h3>
        <p className="text-xs t-text-faint leading-relaxed mb-2">
          选择要随下一条消息发送的文件（单文件 ≤ 10MB）。
          <br />
          文本类（{SUPPORTED_TEXT}）直接读取；二进制类（{SUPPORTED_BINARY}）自动提取文本。
        </p>
        <label className="flex flex-col items-center justify-center gap-2 py-5 border-2 border-dashed t-border-strong rounded-xl cursor-pointer t-hover-border-accent t-hover-bg t-hover-text-accent transition-colors t-text-faint">
          <UploadCloud className="w-8 h-8" />
          <span className="text-xs">点击选择文件（仅本次发送）</span>
          <input
            type="file"
            multiple
            className="hidden"
            onChange={(e) => { if (e.target.files?.length) onAddFiles(e.target.files); e.target.value = '' }}
          />
        </label>
        {pendingFiles.length > 0 && (
          <div className="space-y-2 mt-2">
            <p className="text-xs t-text-faint">待发送（{pendingFiles.length}）</p>
            {pendingFiles.map((file, index) => (
              <div key={index} className="flex items-center gap-2.5 px-3 py-2.5 t-bg-panel border t-border rounded-lg">
                <FileText className="w-4 h-4 t-text-accent shrink-0" />
                <div className="flex-1 min-w-0">
                  <p className="text-xs t-text-2 truncate" title={file.filename}>{file.filename}</p>
                  <p className="text-[10px] t-text-faint">{formatSize(file.size)}{file.content ? ' · 已解析' : ' · 无文本内容'}</p>
                </div>
                <button onClick={() => onRemoveFile(index)} className="t-text-faint t-hover-text-danger shrink-0" title="移除">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            <p className="text-[10px] t-text-fainter flex items-center gap-1.5">
              <Paperclip className="w-3 h-3" /> 文件将随下一条消息一起发送，发送后自动清空
            </p>
          </div>
        )}
      </div>

      {/* 我的文件库：持久化，可在会话中复用 */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <h3 className="text-sm font-semibold t-text-2">我的文件</h3>
          <button onClick={onFilesChange} title="刷新" className="t-text-faint t-hover-text">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
        <p className="text-xs t-text-faint leading-relaxed mb-2">
          上传到文件库后永久保存，可在任意会话中复用（点击「加入会话」）。
        </p>

        <label className="flex flex-col items-center justify-center gap-2 py-4 border-2 border-dashed t-border-strong rounded-xl cursor-pointer t-hover-border-accent t-hover-bg t-hover-text-accent transition-colors t-text-faint">
          <UploadCloud className="w-7 h-7" />
          <span className="text-xs">{uploading ? '上传中...' : '上传到文件库（持久保存）'}</span>
          <input
            type="file"
            multiple
            className="hidden"
            onChange={(e) => { if (e.target.files?.length) handleUpload(e.target.files); e.target.value = '' }}
          />
        </label>

        {error && <p className="text-[11px] text-red-500 mt-1.5">{error}</p>}

        {files.length === 0 ? (
          <p className="text-xs t-text-fainter text-center py-4">文件库为空</p>
        ) : (
          <div className="space-y-2 mt-2">
            {files.map((file) => (
              <div key={file.id} className="px-3 py-2.5 t-bg-panel border t-border rounded-lg">
                <div className="flex items-center gap-2.5">
                  <FileText className="w-4 h-4 t-text-accent shrink-0" />
                  <div className="flex-1 min-w-0">
                    <button onClick={() => setViewing({ id: file.id, filename: file.filename })}
                      className="text-xs t-text-2 truncate hover:underline text-left" title="点击查看内容">
                      {file.filename}
                    </button>
                    <p className="text-[10px] t-text-faint">{formatSize(file.file_size)} · {fmtTime(file.created_at)}</p>
                  </div>
                </div>
                <div className="flex items-center gap-1 mt-1.5">
                  <button
                    onClick={() => setViewing({ id: file.id, filename: file.filename })}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md t-text-2 border t-border-strong t-hover-card"
                    title="查看内容"
                  >
                    <Eye className="w-3 h-3" /> 查看
                  </button>
                  <button
                    onClick={() => reuse(file)}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md t-bg-accent/10 t-text-accent t-hover-bg"
                    title="加入当前会话作为附件"
                  >
                    <PlusCircle className="w-3 h-3" /> 加入会话
                  </button>
                  <button
                    onClick={() => remove(file)}
                    className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md t-text-faint t-hover-text-danger t-hover-bg"
                    title="删除"
                  >
                    <Trash2 className="w-3 h-3" /> 删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {viewing && <FileViewer file={viewing} onClose={() => setViewing(null)} />}
    </div>
  )
}

export default FilesTab

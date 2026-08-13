import { useState, useEffect } from 'react'
import { Upload, Trash2, Download, FileText, Search, RefreshCw } from 'lucide-react'

function AttachmentManager() {
  const [attachments, setAttachments] = useState([])
  const [filter, setFilter] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    loadAttachments()
  }, [])

  const loadAttachments = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/attachments/list')
      const result = await response.json()
      if (result.success) {
        setAttachments(result.attachments || [])
      }
    } catch (error) {
      console.error('加载附件失败:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleUploadFile = async (e) => {
    const files = e.target.files
    if (!files || files.length === 0) return

    for (const file of files) {
      const formData = new FormData()
      formData.append('file', file)

      try {
        const response = await fetch('/api/attachments/upload', {
          method: 'POST',
          body: formData,
        })
        const result = await response.json()
        if (result.success) {
          loadAttachments()
        }
      } catch (error) {
        console.error('上传附件失败:', error)
      }
    }
  }

  const handleDeleteAttachment = async (attachmentId) => {
    if (!confirm('确定删除此附件？')) return
    try {
      const response = await fetch('/api/attachments/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ attachment_id: attachmentId }),
      })
      const result = await response.json()
      if (result.success) {
        loadAttachments()
      }
    } catch (error) {
      console.error('删除附件失败:', error)
    }
  }

  const filteredAttachments = attachments.filter(attachment =>
    attachment.filename?.toLowerCase().includes(filter.toLowerCase()) ||
    attachment.description?.toLowerCase().includes(filter.toLowerCase())
  )

  const formatSize = (size) => {
    if (!size) return '0 B'
    const units = ['B', 'KB', 'MB', 'GB']
    let index = 0
    while (size >= 1024 && index < units.length - 1) {
      size /= 1024
      index++
    }
    return size.toFixed(2) + ' ' + units[index]
  }

  const getFileIcon = (filename) => {
    const ext = filename?.split('.').pop()?.toLowerCase()
    if (['pdf'].includes(ext)) return 'text-red-500'
    if (['doc', 'docx'].includes(ext)) return 'text-blue-500'
    if (['xls', 'xlsx', 'csv'].includes(ext)) return 'text-green-500'
    if (['ppt', 'pptx'].includes(ext)) return 'text-orange-500'
    if (['txt', 'md'].includes(ext)) return 'text-gray-500'
    if (['jpg', 'jpeg', 'png', 'gif', 'bmp'].includes(ext)) return 'text-purple-500'
    return 'text-gray-400'
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">附件管理</h1>
          <p className="text-gray-500 mt-1">管理上传的文件附件</p>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors cursor-pointer">
            <Upload className="w-4 h-4" />
            上传文件
            <input type="file" multiple className="hidden" onChange={handleUploadFile} />
          </label>
          <button
            onClick={loadAttachments}
            disabled={loading}
            className="flex items-center gap-2 px-4 py-2 border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </div>

      {/* Filter */}
      <div className="mb-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
          <input
            type="text"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="搜索文件名..."
            className="w-full pl-10 pr-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
          />
        </div>
      </div>

      {/* Attachment List */}
      <div className="flex-1 overflow-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filteredAttachments.map((attachment) => (
            <div
              key={attachment.id}
              className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start gap-3">
                <div className={`p-3 rounded-lg bg-gray-50 ${getFileIcon(attachment.filename)}`}>
                  <FileText className="w-8 h-8" />
                </div>
                <div className="flex-1 min-w-0">
                  <h3 className="text-sm font-medium text-gray-800 truncate" title={attachment.filename}>
                    {attachment.filename}
                  </h3>
                  <p className="text-xs text-gray-500 mt-1">{formatSize(attachment.size)}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {attachment.created_at ? new Date(attachment.created_at).toLocaleString('zh-CN') : '-'}
                  </p>
                </div>
                <div className="flex flex-col gap-1">
                  <button
                    onClick={() => {
                      window.open(`/api/attachments/download/${attachment.id}`, '_blank')
                    }}
                    className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    title="下载"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDeleteAttachment(attachment.id)}
                    className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    title="删除"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
          {filteredAttachments.length === 0 && (
            <div className="col-span-full flex flex-col items-center justify-center py-12 text-gray-400">
              <div className="w-16 h-16 rounded-full bg-gray-100 flex items-center justify-center mb-4">
                <FileText className="w-8 h-8" />
              </div>
              <p className="text-lg font-medium">暂无附件</p>
              <p className="text-sm">点击上方按钮上传文件</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default AttachmentManager

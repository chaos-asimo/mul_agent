import { Paperclip, FileText, X, UploadCloud } from 'lucide-react'
import { formatSize } from '../api/client'

const SUPPORTED_TEXT = 'txt / md / json / py / js / html / css / xml / csv'
const SUPPORTED_BINARY = 'pdf / doc(x) / xls(x) / ppt(x)'

function FilesTab({ pendingFiles, onAddFiles, onRemoveFile }) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold t-text-2 mb-1">附件文件</h3>
        <p className="text-xs t-text-faint leading-relaxed">
          选择要随下一条消息发送的文件（单文件 ≤ 10MB）。
          <br />
          文本类（{SUPPORTED_TEXT}）直接读取；二进制类（{SUPPORTED_BINARY}）自动提取文本。
        </p>
      </div>

      <label className="flex flex-col items-center justify-center gap-2 py-6 border-2 border-dashed t-border-strong rounded-xl cursor-pointer t-hover-border-accent t-hover-bg t-hover-text-accent transition-colors t-text-faint">
        <UploadCloud className="w-8 h-8" />
        <span className="text-xs">点击选择文件</span>
        <input
          type="file"
          multiple
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) onAddFiles(e.target.files)
            e.target.value = ''
          }}
        />
      </label>

      {pendingFiles.length === 0 ? (
        <p className="text-xs t-text-fainter text-center py-4">暂无待发送文件</p>
      ) : (
        <div className="space-y-2">
          <p className="text-xs t-text-faint">待发送（{pendingFiles.length}）</p>
          {pendingFiles.map((file, index) => (
            <div
              key={index}
              className="flex items-center gap-2.5 px-3 py-2.5 t-bg-panel border t-border rounded-lg"
            >
              <FileText className="w-4 h-4 t-text-accent shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs t-text-2 truncate" title={file.filename}>
                  {file.filename}
                </p>
                <p className="text-[10px] t-text-faint">
                  {formatSize(file.size)}
                  {file.content ? ' · 已解析' : ' · 无文本内容'}
                </p>
              </div>
              <button
                onClick={() => onRemoveFile(index)}
                className="t-text-faint t-hover-text-danger shrink-0"
                title="移除"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
          <p className="text-[10px] t-text-fainter flex items-center gap-1.5">
            <Paperclip className="w-3 h-3" />
            文件将随下一条消息一起发送，发送后自动清空
          </p>
        </div>
      )}
    </div>
  )
}

export default FilesTab

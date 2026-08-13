import { useState, useEffect } from 'react'
import { Plus, Edit, Trash2, Play, Save, X, ChevronRight } from 'lucide-react'

function ScriptManager() {
  const [scripts, setScripts] = useState([])
  const [editingScript, setEditingScript] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [newScript, setNewScript] = useState({ name: '', description: '', code: '' })
  const [filter, setFilter] = useState('')

  useEffect(() => {
    loadScripts()
  }, [])

  const loadScripts = async () => {
    try {
      const response = await fetch('/api/scripts/list')
      const result = await response.json()
      if (result.success) {
        setScripts(result.scripts)
      }
    } catch (error) {
      console.error('加载脚本失败:', error)
    }
  }

  const handleCreateScript = async () => {
    try {
      const response = await fetch('/api/scripts/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newScript),
      })
      const result = await response.json()
      if (result.success) {
        loadScripts()
        setNewScript({ name: '', description: '', code: '' })
        setShowModal(false)
      }
    } catch (error) {
      console.error('创建脚本失败:', error)
    }
  }

  const handleUpdateScript = async () => {
    if (!editingScript) return
    try {
      const response = await fetch('/api/scripts/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingScript),
      })
      const result = await response.json()
      if (result.success) {
        loadScripts()
        setEditingScript(null)
      }
    } catch (error) {
      console.error('更新脚本失败:', error)
    }
  }

  const handleDeleteScript = async (scriptId) => {
    if (!confirm('确定删除此脚本？')) return
    try {
      const response = await fetch('/api/scripts/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_id: scriptId }),
      })
      const result = await response.json()
      if (result.success) {
        loadScripts()
      }
    } catch (error) {
      console.error('删除脚本失败:', error)
    }
  }

  const handleRunScript = async (scriptId) => {
    try {
      const response = await fetch('/api/scripts/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_id: scriptId }),
      })
      const result = await response.json()
      if (result.success) {
        alert('脚本执行成功')
      } else {
        alert(`脚本执行失败: ${result.message}`)
      }
    } catch (error) {
      console.error('执行脚本失败:', error)
    }
  }

  const filteredScripts = scripts.filter(script =>
    script.name.toLowerCase().includes(filter.toLowerCase()) ||
    script.description.toLowerCase().includes(filter.toLowerCase())
  )

  const highlightPython = (code) => {
    if (!code) return ''
    const keywords = ['def', 'class', 'if', 'elif', 'else', 'for', 'while', 'return', 'import', 'from', 'as', 'try', 'except', 'finally', 'with', 'lambda', 'yield', 'async', 'await', 'True', 'False', 'None']
    let result = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
    
    keywords.forEach(keyword => {
      const regex = new RegExp(`\\b(${keyword})\\b`, 'g')
      result = result.replace(regex, '<span class="text-purple-600 font-medium">$1</span>')
    })
    
    result = result.replace(/("#.*")|('.*')/g, '<span class="text-green-600">$1$2</span>')
    result = result.replace(/(\/\/.*$)/gm, '<span class="text-gray-400 italic">$1</span>')
    result = result.replace(/(\d+)/g, '<span class="text-orange-600">$1</span>')
    
    return result
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">脚本管理</h1>
          <p className="text-gray-500 mt-1">管理和运行自定义Python脚本</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-5 h-5" />
          创建脚本
        </button>
      </div>

      {/* Filter */}
      <div className="mb-4">
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="搜索脚本名称或描述..."
          className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
        />
      </div>

      {/* Script List */}
      <div className="flex-1 overflow-auto space-y-3">
        {filteredScripts.map((script) => (
          <div
            key={script.id}
            className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md transition-shadow"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-semibold text-gray-800">{script.name}</h3>
                  <span className="px-2 py-0.5 bg-gray-100 text-gray-500 text-xs rounded-full">
                    {script.language || 'Python'}
                  </span>
                </div>
                <p className="text-gray-500 mt-1">{script.description}</p>
                <pre className="mt-3 p-3 bg-gray-50 rounded-lg text-sm overflow-x-auto max-h-32 overflow-y-auto">
                  <code dangerouslySetInnerHTML={{ __html: highlightPython(script.code.substring(0, 200) + (script.code.length > 200 ? '...' : '')) }} />
                </pre>
              </div>
              <div className="flex flex-col gap-2 ml-4">
                <button
                  onClick={() => {
                    setEditingScript(script)
                    setShowModal(true)
                  }}
                  className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                  title="编辑"
                >
                  <Edit className="w-5 h-5" />
                </button>
                <button
                  onClick={() => handleRunScript(script.id)}
                  className="p-2 text-gray-500 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                  title="运行"
                >
                  <Play className="w-5 h-5" />
                </button>
                <button
                  onClick={() => handleDeleteScript(script.id)}
                  className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                  title="删除"
                >
                  <Trash2 className="w-5 h-5" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h2 className="text-xl font-semibold text-gray-800">
                {editingScript ? '编辑脚本' : '创建脚本'}
              </h2>
              <button
                onClick={() => {
                  setShowModal(false)
                  setEditingScript(null)
                  setNewScript({ name: '', description: '', code: '' })
                }}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-auto p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">脚本名称</label>
                <input
                  type="text"
                  value={editingScript?.name || newScript.name}
                  onChange={(e) => {
                    if (editingScript) {
                      setEditingScript({ ...editingScript, name: e.target.value })
                    } else {
                      setNewScript({ ...newScript, name: e.target.value })
                    }
                  }}
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  placeholder="输入脚本名称"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">脚本描述</label>
                <textarea
                  value={editingScript?.description || newScript.description}
                  onChange={(e) => {
                    if (editingScript) {
                      setEditingScript({ ...editingScript, description: e.target.value })
                    } else {
                      setNewScript({ ...newScript, description: e.target.value })
                    }
                  }}
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none resize-none"
                  rows={3}
                  placeholder="输入脚本描述"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">脚本代码</label>
                <div className="relative">
                  <textarea
                    value={editingScript?.code || newScript.code}
                    onChange={(e) => {
                      if (editingScript) {
                        setEditingScript({ ...editingScript, code: e.target.value })
                      } else {
                        setNewScript({ ...newScript, code: e.target.value })
                      }
                    }}
                    className="w-full px-4 py-3 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none font-mono text-sm resize-none h-80"
                    placeholder="# 输入Python脚本代码..."
                  />
                </div>
              </div>
            </div>
            
            <div className="p-4 border-t border-gray-200 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowModal(false)
                  setEditingScript(null)
                  setNewScript({ name: '', description: '', code: '' })
                }}
                className="px-4 py-2 border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors"
              >
                取消
              </button>
              <button
                onClick={editingScript ? handleUpdateScript : handleCreateScript}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Save className="w-4 h-4" />
                {editingScript ? '保存修改' : '创建脚本'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ScriptManager

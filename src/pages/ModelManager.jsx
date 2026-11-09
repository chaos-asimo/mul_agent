import { useState, useEffect } from 'react'
import { Plus, Edit, Trash2, Save, X, Check } from 'lucide-react'

function ModelManager() {
  const [models, setModels] = useState([])
  const [editingModel, setEditingModel] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [newModel, setNewModel] = useState({ name: '', api_key: '', base_url: '', description: '' })

  useEffect(() => {
    loadModels()
  }, [])

  const loadModels = async () => {
    try {
      const response = await fetch('/api/models/list')
      const result = await response.json()
      if (result.success) {
        setModels(result.models)
      }
    } catch (error) {
      console.error('加载模型失败:', error)
    }
  }

  const handleCreateModel = async () => {
    try {
      const response = await fetch('/api/models/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newModel),
      })
      const result = await response.json()
      if (result.success) {
        loadModels()
        setNewModel({ name: '', api_key: '', base_url: '', description: '' })
        setShowModal(false)
      }
    } catch (error) {
      console.error('创建模型失败:', error)
    }
  }

  const handleUpdateModel = async () => {
    if (!editingModel) return
    try {
      const response = await fetch('/api/models/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingModel),
      })
      const result = await response.json()
      if (result.success) {
        loadModels()
        setEditingModel(null)
      }
    } catch (error) {
      console.error('更新模型失败:', error)
    }
  }

  const handleDeleteModel = async (modelId) => {
    if (!confirm('确定删除此模型？')) return
    try {
      const response = await fetch('/api/models/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_id: modelId }),
      })
      const result = await response.json()
      if (result.success) {
        loadModels()
      }
    } catch (error) {
      console.error('删除模型失败:', error)
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">模型管理</h1>
          <p className="text-gray-500 mt-1">管理AI模型配置</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-5 h-5" />
          添加模型
        </button>
      </div>

      {/* Model List */}
      <div className="flex-1 overflow-auto">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {models.map((model) => (
            <div
              key={model.id}
              className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="text-lg font-semibold text-gray-800">{model.name}</h3>
                  <p className="text-gray-500 text-sm mt-1">{model.description}</p>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setEditingModel(model)
                      setShowModal(true)
                    }}
                    className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                    title="编辑"
                  >
                    <Edit className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => handleDeleteModel(model.id)}
                    className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                    title="删除"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
              
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className="text-gray-400">API Key:</span>
                  <span className="text-gray-600 font-mono">
                    {model.api_key ? '***' + model.api_key.slice(-4) : '未设置'}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-gray-400">Base URL:</span>
                  <span className="text-gray-600 truncate">{model.base_url || '-'}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h2 className="text-xl font-semibold text-gray-800">
                {editingModel ? '编辑模型' : '添加模型'}
              </h2>
              <button
                onClick={() => {
                  setShowModal(false)
                  setEditingModel(null)
                  setNewModel({ name: '', api_key: '', base_url: '', description: '' })
                }}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-auto p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">模型名称</label>
                <input
                  type="text"
                  value={editingModel?.name || newModel.name}
                  onChange={(e) => {
                    if (editingModel) {
                      setEditingModel({ ...editingModel, name: e.target.value })
                    } else {
                      setNewModel({ ...newModel, name: e.target.value })
                    }
                  }}
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  placeholder="输入模型名称"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">API Key</label>
                <input
                  type="password"
                  value={editingModel?.api_key || newModel.api_key}
                  onChange={(e) => {
                    if (editingModel) {
                      setEditingModel({ ...editingModel, api_key: e.target.value })
                    } else {
                      setNewModel({ ...newModel, api_key: e.target.value })
                    }
                  }}
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  placeholder="输入API Key"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Base URL</label>
                <input
                  type="text"
                  value={editingModel?.base_url || newModel.base_url}
                  onChange={(e) => {
                    if (editingModel) {
                      setEditingModel({ ...editingModel, base_url: e.target.value })
                    } else {
                      setNewModel({ ...newModel, base_url: e.target.value })
                    }
                  }}
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  placeholder="输入Base URL"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">描述</label>
                <textarea
                  value={editingModel?.description || newModel.description}
                  onChange={(e) => {
                    if (editingModel) {
                      setEditingModel({ ...editingModel, description: e.target.value })
                    } else {
                      setNewModel({ ...newModel, description: e.target.value })
                    }
                  }}
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none resize-none"
                  rows={3}
                  placeholder="输入模型描述"
                />
              </div>
            </div>
            
            <div className="p-4 border-t border-gray-200 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowModal(false)
                  setEditingModel(null)
                  setNewModel({ name: '', api_key: '', base_url: '', description: '' })
                }}
                className="px-4 py-2 border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors"
              >
                取消
              </button>
              <button
                onClick={editingModel ? handleUpdateModel : handleCreateModel}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Save className="w-4 h-4" />
                {editingModel ? '保存修改' : '添加模型'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default ModelManager

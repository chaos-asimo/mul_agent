import { useState, useEffect } from 'react'
import { Plus, Edit, Trash2, Play, Save, X, ChevronRight } from 'lucide-react'

function AgentManager() {
  const [agents, setAgents] = useState([])
  const [editingAgent, setEditingAgent] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [newAgent, setNewAgent] = useState({ name: '', description: '', config: '' })

  useEffect(() => {
    loadAgents()
  }, [])

  const loadAgents = async () => {
    try {
      const response = await fetch('/api/agents/list')
      const result = await response.json()
      if (result.success) {
        setAgents(result.agents)
      }
    } catch (error) {
      console.error('加载Agent失败:', error)
    }
  }

  const handleCreateAgent = async () => {
    try {
      const response = await fetch('/api/agents/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newAgent),
      })
      const result = await response.json()
      if (result.success) {
        loadAgents()
        setNewAgent({ name: '', description: '', config: '' })
        setShowModal(false)
      }
    } catch (error) {
      console.error('创建Agent失败:', error)
    }
  }

  const handleUpdateAgent = async () => {
    if (!editingAgent) return
    try {
      const response = await fetch('/api/agents/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingAgent),
      })
      const result = await response.json()
      if (result.success) {
        loadAgents()
        setEditingAgent(null)
      }
    } catch (error) {
      console.error('更新Agent失败:', error)
    }
  }

  const handleDeleteAgent = async (agentId) => {
    if (!confirm('确定删除此Agent？')) return
    try {
      const response = await fetch('/api/agents/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId }),
      })
      const result = await response.json()
      if (result.success) {
        loadAgents()
      }
    } catch (error) {
      console.error('删除Agent失败:', error)
    }
  }

  const handleRunAgent = async (agentId) => {
    try {
      const response = await fetch('/api/agents/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId }),
      })
      const result = await response.json()
      if (result.success) {
        alert('Agent执行成功')
      } else {
        alert(`Agent执行失败: ${result.message}`)
      }
    } catch (error) {
      console.error('执行Agent失败:', error)
    }
  }

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Agent管理</h1>
          <p className="text-gray-500 mt-1">管理和运行AI Agent</p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-5 h-5" />
          创建Agent
        </button>
      </div>

      {/* Agent List */}
      <div className="flex-1 overflow-auto space-y-3">
        {agents.map((agent) => (
          <div
            key={agent.id}
            className="bg-white border border-gray-200 rounded-xl p-4 hover:shadow-md transition-shadow"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-lg font-semibold text-gray-800">{agent.name}</h3>
                  <span className="px-2 py-0.5 bg-green-100 text-green-600 text-xs rounded-full">
                    活跃
                  </span>
                </div>
                <p className="text-gray-500 mt-1">{agent.description}</p>
                <pre className="mt-3 p-3 bg-gray-50 rounded-lg text-sm overflow-x-auto max-h-32 overflow-y-auto">
                  <code>{agent.config ? JSON.stringify(JSON.parse(agent.config), null, 2).substring(0, 300) + (JSON.stringify(JSON.parse(agent.config)).length > 300 ? '...' : '') : '{}'}</code>
                </pre>
              </div>
              <div className="flex flex-col gap-2 ml-4">
                <button
                  onClick={() => {
                    setEditingAgent(agent)
                    setShowModal(true)
                  }}
                  className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                  title="编辑"
                >
                  <Edit className="w-5 h-5" />
                </button>
                <button
                  onClick={() => handleRunAgent(agent.id)}
                  className="p-2 text-gray-500 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                  title="运行"
                >
                  <Play className="w-5 h-5" />
                </button>
                <button
                  onClick={() => handleDeleteAgent(agent.id)}
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
          <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h2 className="text-xl font-semibold text-gray-800">
                {editingAgent ? '编辑Agent' : '创建Agent'}
              </h2>
              <button
                onClick={() => {
                  setShowModal(false)
                  setEditingAgent(null)
                  setNewAgent({ name: '', description: '', config: '' })
                }}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-auto p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Agent名称</label>
                <input
                  type="text"
                  value={editingAgent?.name || newAgent.name}
                  onChange={(e) => {
                    if (editingAgent) {
                      setEditingAgent({ ...editingAgent, name: e.target.value })
                    } else {
                      setNewAgent({ ...newAgent, name: e.target.value })
                    }
                  }}
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  placeholder="输入Agent名称"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">Agent描述</label>
                <textarea
                  value={editingAgent?.description || newAgent.description}
                  onChange={(e) => {
                    if (editingAgent) {
                      setEditingAgent({ ...editingAgent, description: e.target.value })
                    } else {
                      setNewAgent({ ...newAgent, description: e.target.value })
                    }
                  }}
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none resize-none"
                  rows={3}
                  placeholder="输入Agent描述"
                />
              </div>
              
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">配置（JSON）</label>
                <textarea
                  value={editingAgent?.config || newAgent.config}
                  onChange={(e) => {
                    if (editingAgent) {
                      setEditingAgent({ ...editingAgent, config: e.target.value })
                    } else {
                      setNewAgent({ ...newAgent, config: e.target.value })
                    }
                  }}
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none font-mono text-sm resize-none h-64"
                  placeholder="{}"
                />
              </div>
            </div>
            
            <div className="p-4 border-t border-gray-200 flex justify-end gap-3">
              <button
                onClick={() => {
                  setShowModal(false)
                  setEditingAgent(null)
                  setNewAgent({ name: '', description: '', config: '' })
                }}
                className="px-4 py-2 border border-gray-200 text-gray-600 rounded-lg hover:bg-gray-50 transition-colors"
              >
                取消
              </button>
              <button
                onClick={editingAgent ? handleUpdateAgent : handleCreateAgent}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Save className="w-4 h-4" />
                {editingAgent ? '保存修改' : '创建Agent'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default AgentManager

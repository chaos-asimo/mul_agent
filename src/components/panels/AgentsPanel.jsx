import { useState, useEffect } from 'react';
import { Users, Plus, Edit2, Trash2, Save, X, GripVertical } from 'lucide-react';

function AgentsPanel() {
  const [agents, setAgents] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editingAgent, setEditingAgent] = useState(null);
  const [newAgent, setNewAgent] = useState({
    id: '',
    name: '',
    role_description: '',
    model_id: '',
    enabled: true,
    order: 0,
  });
  const [models, setModels] = useState([]);

  useEffect(() => {
    loadAgents();
    loadModels();
  }, []);

  const loadAgents = async () => {
    try {
      const response = await fetch('/api/agents');
      const result = await response.json();
      if (result.groups && Array.isArray(result.groups)) {
        const allAgents = [];
        result.groups.forEach(group => {
          if (group.agents) {
            group.agents.forEach(agent => {
              allAgents.push({ ...agent, group: group.name, groupColor: group.color });
            });
          }
        });
        setAgents(allAgents.sort((a, b) => (a.order || 0) - (b.order || 0)));
      }
    } catch (error) {
      console.error('加载Agent失败:', error);
    }
  };

  const loadModels = async () => {
    try {
      const response = await fetch('/api/models');
      const result = await response.json();
      if (Array.isArray(result)) {
        setModels(result.filter(m => m.enabled !== false));
      }
    } catch (error) {
      console.error('加载模型失败:', error);
    }
  };

  const openModal = (agent = null) => {
    if (agent) {
      setEditingAgent(agent);
      setNewAgent({
        id: agent.id || '',
        name: agent.name || '',
        role_description: agent.role_description || '',
        model_id: agent.model_id || '',
        enabled: agent.enabled !== false,
        order: agent.order || 0,
      });
    } else {
      setEditingAgent(null);
      setNewAgent({
        id: '',
        name: '',
        role_description: '',
        model_id: '',
        enabled: true,
        order: agents.length,
      });
    }
    setShowModal(true);
  };

  const saveAgent = async () => {
    if (!newAgent.name.trim()) {
      alert('请输入Agent名称');
      return;
    }

    try {
      const endpoint = editingAgent ? `/api/agents/${editingAgent.id}` : '/api/agents';
      const method = editingAgent ? 'PUT' : 'POST';

      const response = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newAgent),
      });

      const result = await response.json();

      if (result.status === 'success') {
        loadAgents();
        setShowModal(false);
      } else {
        alert(result.message || '保存失败');
      }
    } catch (error) {
      console.error('保存Agent失败:', error);
      alert('保存失败: ' + error.message);
    }
  };

  const deleteAgent = async (agentId) => {
    if (!confirm('确定删除此Agent？')) return;
    try {
      const response = await fetch(`/api/agents/${agentId}`, { method: 'DELETE' });
      const result = await response.json();
      if (result.status === 'success') {
        loadAgents();
      }
    } catch (error) {
      console.error('删除Agent失败:', error);
    }
  };

  const handleChange = (field, value) => {
    setNewAgent(prev => ({ ...prev, [field]: value }));
  };

  const groupedAgents = agents.reduce((acc, agent) => {
    const group = agent.group || '未分组';
    if (!acc[group]) {
      acc[group] = { color: agent.groupColor || '#667eea', agents: [] };
    }
    acc[group].agents.push(agent);
    return acc;
  }, {});

  return (
    <div className="h-full flex flex-col bg-white p-4">
      {/* 顶部标题 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Users className="w-6 h-6 text-cyan-600" />
          <h2 className="text-lg font-semibold text-gray-800">Agent配置</h2>
        </div>
        <button
          onClick={() => openModal()}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" /> 添加Agent
        </button>
      </div>

      {/* Agent列表 */}
      <div className="flex-1 overflow-y-auto">
        {Object.entries(groupedAgents).map(([groupName, groupData]) => (
          <div key={groupName} className="mb-6">
            <h3 className="text-sm font-medium mb-3 flex items-center gap-2" style={{ color: groupData.color }}>
              <span className="w-2 h-2 rounded-full" style={{ backgroundColor: groupData.color }}></span>
              {groupName} ({groupData.agents.length})
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {groupData.agents.map((agent, index) => (
                <div key={agent.id} className="border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow">
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs text-gray-400 cursor-move">
                      <GripVertical className="w-4 h-4" />
                    </span>
                    <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-500 rounded">#{index + 1}</span>
                    <h4 className="font-medium text-gray-800 flex-1">{agent.name}</h4>
                    <span className={`text-xs px-2 py-0.5 rounded ${agent.enabled ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-500'}`}>
                      {agent.enabled ? '已启用' : '已禁用'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mb-1">绑定模型: {agent.model_name || agent.model_id || '未绑定'}</p>
                  <p className="text-xs text-gray-500 line-clamp-2">{agent.role_description}</p>
                  <div className="flex gap-2 mt-3">
                    <button onClick={() => openModal(agent)} className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-lg">
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteAgent(agent.id)} className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        {agents.length === 0 && (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <Users className="w-12 h-12 mb-3" />
            <p>暂无Agent配置</p>
            <p className="text-sm">点击上方按钮添加Agent</p>
          </div>
        )}
      </div>

      {/* Agent配置模态框 */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={() => setShowModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Users className="w-5 h-5" /> {editingAgent ? '编辑Agent' : '添加Agent'}
              </h3>
              <button onClick={() => setShowModal(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Agent名称 <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  value={newAgent.name}
                  onChange={(e) => handleChange('name', e.target.value)}
                  placeholder="输入Agent名称"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">角色描述</label>
                <textarea
                  value={newAgent.role_description}
                  onChange={(e) => handleChange('role_description', e.target.value)}
                  placeholder="描述此Agent的角色和职责..."
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">绑定模型</label>
                <select
                  value={newAgent.model_id}
                  onChange={(e) => handleChange('model_id', e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                >
                  <option value="">未绑定</option>
                  {models.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name} ({model.model_name})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={newAgent.enabled}
                  onChange={(e) => handleChange('enabled', e.target.checked)}
                  className="w-4 h-4"
                />
                <label className="text-sm text-gray-700">启用此Agent</label>
              </div>
            </div>
            <div className="flex justify-end gap-3 px-4 py-3 border-t border-gray-200">
              <button onClick={() => setShowModal(false)} className="px-4 py-2 text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200">
                取消
              </button>
              <button onClick={saveAgent} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                <Save className="w-4 h-4" /> 保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AgentsPanel;
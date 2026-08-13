import { useState, useEffect } from 'react';
import { Cog, Plus, Edit2, Trash2, Save, X, Eye, EyeOff } from 'lucide-react';

function ModelsPanel() {
  const [models, setModels] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editingModel, setEditingModel] = useState(null);
  const [newModel, setNewModel] = useState({
    id: '',
    name: '',
    model_type: 'text',
    api_type: 'openai',
    api_url: '',
    api_key: '',
    model_name: '',
    enabled: true,
  });
  const [showApiKey, setShowApiKey] = useState(false);

  useEffect(() => {
    loadModels();
  }, []);

  const loadModels = async () => {
    try {
      const response = await fetch('/api/models');
      const result = await response.json();
      if (Array.isArray(result)) {
        setModels(result);
      }
    } catch (error) {
      console.error('加载模型失败:', error);
    }
  };

  const openModal = (model = null) => {
    if (model) {
      setEditingModel(model);
      setNewModel({
        id: model.id || '',
        name: model.name || '',
        model_type: model.model_type || 'text',
        api_type: model.api_type || 'openai',
        api_url: model.api_url || '',
        api_key: model.api_key || '',
        model_name: model.model_name || '',
        enabled: model.enabled !== false,
      });
    } else {
      setEditingModel(null);
      setNewModel({
        id: '',
        name: '',
        model_type: 'text',
        api_type: 'openai',
        api_url: '',
        api_key: '',
        model_name: '',
        enabled: true,
      });
    }
    setShowModal(true);
  };

  const saveModel = async () => {
    if (!newModel.name.trim()) {
      alert('请输入模型名称');
      return;
    }

    try {
      const endpoint = editingModel ? `/api/models/${editingModel.id}` : '/api/models';
      const method = editingModel ? 'PUT' : 'POST';

      const response = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newModel),
      });

      const result = await response.json();

      if (result.status === 'success') {
        loadModels();
        setShowModal(false);
      } else {
        alert(result.message || '保存失败');
      }
    } catch (error) {
      console.error('保存模型失败:', error);
      alert('保存失败: ' + error.message);
    }
  };

  const deleteModel = async (modelId) => {
    if (!confirm('确定删除此模型？')) return;
    try {
      const response = await fetch(`/api/models/${modelId}`, { method: 'DELETE' });
      const result = await response.json();
      if (result.status === 'success') {
        loadModels();
      }
    } catch (error) {
      console.error('删除模型失败:', error);
    }
  };

  const handleChange = (field, value) => {
    setNewModel(prev => ({ ...prev, [field]: value }));
  };

  const groupedModels = {
    text: models.filter(m => m.model_type === 'text'),
    image: models.filter(m => m.model_type === 'image'),
    video: models.filter(m => m.model_type === 'video'),
  };

  return (
    <div className="h-full flex flex-col bg-white p-4">
      {/* 顶部标题 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Cog className="w-6 h-6 text-gray-600" />
          <h2 className="text-lg font-semibold text-gray-800">模型配置</h2>
        </div>
        <button
          onClick={() => openModal()}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-4 h-4" /> 添加模型
        </button>
      </div>

      {/* 模型列表 */}
      <div className="flex-1 overflow-y-auto">
        {/* 文本模型 */}
        {groupedModels.text.length > 0 && (
          <div className="mb-6">
            <h3 className="text-sm font-medium text-blue-600 mb-3 flex items-center gap-2">
              <span className="w-2 h-2 bg-blue-600 rounded-full"></span> 文本模型 ({groupedModels.text.length})
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {groupedModels.text.map((model) => (
                <div key={model.id} className="border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium text-gray-800">{model.name}</h4>
                    <span className={`text-xs px-2 py-0.5 rounded ${model.enabled ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-500'}`}>
                      {model.enabled ? '已启用' : '已禁用'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mb-1">API类型: {model.api_type}</p>
                  <p className="text-xs text-gray-500 mb-1">模型名称: {model.model_name}</p>
                  <p className="text-xs text-gray-500 truncate">API URL: {model.api_url}</p>
                  <div className="flex gap-2 mt-3">
                    <button onClick={() => openModal(model)} className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-lg">
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteModel(model.id)} className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 图像模型 */}
        {groupedModels.image.length > 0 && (
          <div className="mb-6">
            <h3 className="text-sm font-medium text-green-600 mb-3 flex items-center gap-2">
              <span className="w-2 h-2 bg-green-600 rounded-full"></span> 图像模型 ({groupedModels.image.length})
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {groupedModels.image.map((model) => (
                <div key={model.id} className="border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium text-gray-800">{model.name}</h4>
                    <span className={`text-xs px-2 py-0.5 rounded ${model.enabled ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-500'}`}>
                      {model.enabled ? '已启用' : '已禁用'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mb-1">API类型: {model.api_type}</p>
                  <p className="text-xs text-gray-500 mb-1">模型名称: {model.model_name}</p>
                  <p className="text-xs text-gray-500 truncate">API URL: {model.api_url}</p>
                  <div className="flex gap-2 mt-3">
                    <button onClick={() => openModal(model)} className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-lg">
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteModel(model.id)} className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 视频模型 */}
        {groupedModels.video.length > 0 && (
          <div className="mb-6">
            <h3 className="text-sm font-medium text-yellow-600 mb-3 flex items-center gap-2">
              <span className="w-2 h-2 bg-yellow-600 rounded-full"></span> 视频模型 ({groupedModels.video.length})
            </h3>
            <div className="grid grid-cols-2 gap-3">
              {groupedModels.video.map((model) => (
                <div key={model.id} className="border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-medium text-gray-800">{model.name}</h4>
                    <span className={`text-xs px-2 py-0.5 rounded ${model.enabled ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-500'}`}>
                      {model.enabled ? '已启用' : '已禁用'}
                    </span>
                  </div>
                  <p className="text-xs text-gray-500 mb-1">API类型: {model.api_type}</p>
                  <p className="text-xs text-gray-500 mb-1">模型名称: {model.model_name}</p>
                  <p className="text-xs text-gray-500 truncate">API URL: {model.api_url}</p>
                  <div className="flex gap-2 mt-3">
                    <button onClick={() => openModal(model)} className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-lg">
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button onClick={() => deleteModel(model.id)} className="p-1.5 text-red-600 hover:bg-red-50 rounded-lg">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {models.length === 0 && (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <Cog className="w-12 h-12 mb-3" />
            <p>暂无模型配置</p>
            <p className="text-sm">点击上方按钮添加模型</p>
          </div>
        )}
      </div>

      {/* 模型配置模态框 */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={() => setShowModal(false)}>
          <div className="bg-white rounded-xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Cog className="w-5 h-5" /> {editingModel ? '编辑模型' : '添加模型'}
              </h3>
              <button onClick={() => setShowModal(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">模型名称 <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  value={newModel.name}
                  onChange={(e) => handleChange('name', e.target.value)}
                  placeholder="输入模型名称"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">模型类型</label>
                  <select
                    value={newModel.model_type}
                    onChange={(e) => handleChange('model_type', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  >
                    <option value="text">文本模型</option>
                    <option value="image">图像模型</option>
                    <option value="video">视频模型</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">API类型</label>
                  <select
                    value={newModel.api_type}
                    onChange={(e) => handleChange('api_type', e.target.value)}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  >
                    <option value="openai">OpenAI</option>
                    <option value="claude">Claude</option>
                    <option value="deepseek">DeepSeek</option>
                    <option value="dalle">DALL-E</option>
                    <option value="sd">Stable Diffusion</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">API URL</label>
                <input
                  type="text"
                  value={newModel.api_url}
                  onChange={(e) => handleChange('api_url', e.target.value)}
                  placeholder="https://api.example.com/v1"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
                <div className="relative">
                  <input
                    type={showApiKey ? 'text' : 'password'}
                    value={newModel.api_key}
                    onChange={(e) => handleChange('api_key', e.target.value)}
                    placeholder="输入API密钥"
                    className="w-full px-3 py-2 pr-10 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                  />
                  <button
                    onClick={() => setShowApiKey(!showApiKey)}
                    className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600"
                  >
                    {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">模型名称（Model Name）</label>
                <input
                  type="text"
                  value={newModel.model_name}
                  onChange={(e) => handleChange('model_name', e.target.value)}
                  placeholder="例如：gpt-4o"
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={newModel.enabled}
                  onChange={(e) => handleChange('enabled', e.target.checked)}
                  className="w-4 h-4"
                />
                <label className="text-sm text-gray-700">启用此模型</label>
              </div>
            </div>
            <div className="flex justify-end gap-3 px-4 py-3 border-t border-gray-200">
              <button onClick={() => setShowModal(false)} className="px-4 py-2 text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200">
                取消
              </button>
              <button onClick={saveModel} className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                <Save className="w-4 h-4" /> 保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ModelsPanel;
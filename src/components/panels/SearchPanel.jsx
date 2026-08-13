import { useState, useEffect } from 'react';
import { Search, Plus, Edit2, Trash2, TestTube, X, ExternalLink } from 'lucide-react';

function SearchPanel() {
  const [engines, setEngines] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingEngine, setEditingEngine] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    adapter_type: 'bing',
    api_key: '',
    api_url: '',
    enabled: true
  });

  useEffect(() => {
    loadEngines();
  }, []);

  const loadEngines = async () => {
    try {
      const response = await fetch('/api/search_engines');
      const result = await response.json();
      if (Array.isArray(result)) {
        setEngines(result);
      }
    } catch (error) {
      console.error('加载搜索引擎失败:', error);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      alert('请输入搜索关键词');
      return;
    }
    setIsSearching(true);
    try {
      const response = await fetch('/api/search_test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: searchQuery })
      });
      const result = await response.json();
      if (result.status === 'success') {
        setSearchResults(result.results || []);
      } else {
        setSearchResults([]);
        alert(result.message || '搜索失败');
      }
    } catch (error) {
      console.error('搜索失败:', error);
      setSearchResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  const openModal = (engine = null) => {
    if (engine) {
      setEditingEngine(engine);
      setFormData({
        name: engine.name,
        adapter_type: engine.adapter_type || 'bing',
        api_key: engine.api_key || '',
        api_url: engine.api_url || '',
        enabled: engine.enabled !== false
      });
    } else {
      setEditingEngine(null);
      setFormData({
        name: '',
        adapter_type: 'bing',
        api_key: '',
        api_url: '',
        enabled: true
      });
    }
    setShowModal(true);
  };

  const saveEngine = async () => {
    if (!formData.name.trim()) {
      alert('请输入搜索引擎名称');
      return;
    }
    try {
      const url = editingEngine 
        ? `/api/search_engines/${editingEngine.id}` 
        : '/api/search_engines';
      const method = editingEngine ? 'PUT' : 'POST';
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      const result = await response.json();
      if (result.status === 'success') {
        loadEngines();
        setShowModal(false);
      } else {
        alert(result.message || '保存失败');
      }
    } catch (error) {
      console.error('保存失败:', error);
    }
  };

  const deleteEngine = async (engineId) => {
    if (!confirm('确定要删除这个搜索引擎吗？')) return;
    try {
      const response = await fetch(`/api/search_engines/${engineId}`, {
        method: 'DELETE'
      });
      const result = await response.json();
      if (result.status === 'success') {
        loadEngines();
      } else {
        alert(result.message || '删除失败');
      }
    } catch (error) {
      console.error('删除失败:', error);
    }
  };

  const testEngine = async (engineId) => {
    try {
      const response = await fetch(`/api/search_engines/${engineId}/test`, {
        method: 'POST'
      });
      const result = await response.json();
      if (result.status === 'success') {
        alert('测试成功: ' + result.message);
      } else {
        alert('测试失败: ' + result.message);
      }
    } catch (error) {
      alert('测试失败: ' + error.message);
    }
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 工具栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <Search className="w-5 h-5 text-gray-600" />
          <span className="font-semibold text-gray-800">搜索引擎配置</span>
        </div>
        <button
          onClick={() => openModal()}
          className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
        >
          <Plus className="w-4 h-4" /> 添加搜索引擎
        </button>
      </div>

      <div className="flex-1 flex">
        {/* 左侧：搜索引擎列表 */}
        <div className="w-1/2 border-r border-gray-200 p-4 overflow-auto">
          <h3 className="font-medium text-gray-700 mb-3">搜索引擎列表</h3>
          {engines.length === 0 ? (
            <div className="text-center text-gray-400 py-8">
              <Search className="w-12 h-12 mx-auto mb-3" />
              <p>暂无搜索引擎</p>
              <p className="text-sm mt-1">点击上方按钮添加</p>
            </div>
          ) : (
            <div className="space-y-3">
              {engines.map((engine) => (
                <div
                  key={engine.id}
                  className="border border-gray-200 rounded-lg p-3 hover:border-blue-300 transition-colors"
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-800">{engine.name}</span>
                      <span className={`px-2 py-0.5 rounded text-xs ${
                        engine.enabled 
                          ? 'bg-green-100 text-green-600' 
                          : 'bg-gray-100 text-gray-500'
                      }`}>
                        {engine.enabled ? '已启用' : '已禁用'}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => testEngine(engine.id)}
                        className="p-1.5 text-blue-600 hover:bg-blue-50 rounded"
                        title="测试连接"
                      >
                        <TestTube className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => openModal(engine)}
                        className="p-1.5 text-gray-600 hover:bg-gray-100 rounded"
                        title="编辑"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => deleteEngine(engine.id)}
                        className="p-1.5 text-red-600 hover:bg-red-50 rounded"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                  <div className="text-sm text-gray-500">
                    <div>适配器类型: {engine.adapter_type}</div>
                    {engine.api_url && <div>API URL: {engine.api_url}</div>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 右侧：测试搜索 */}
        <div className="w-1/2 p-4 overflow-auto">
          <h3 className="font-medium text-gray-700 mb-3">测试搜索</h3>
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="输入搜索关键词..."
              className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
            />
            <button
              onClick={handleSearch}
              disabled={isSearching}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {isSearching ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
              ) : (
                <Search className="w-5 h-5" />
              )}
            </button>
          </div>
          <div className="border border-gray-200 rounded-lg p-3 h-64 overflow-auto">
            {searchResults.length === 0 ? (
              <div className="text-center text-gray-400 py-8">
                <Search className="w-8 h-8 mx-auto mb-2" />
                <p>搜索结果将在这里显示</p>
              </div>
            ) : (
              <div className="space-y-3">
                {searchResults.map((result, index) => (
                  <div key={index} className="pb-3 border-b border-gray-100 last:border-0">
                    <h4 className="font-medium text-gray-800 text-sm">
                      {index + 1}. {result.title}
                    </h4>
                    <p className="text-xs text-gray-500 mt-1 line-clamp-2">{result.snippet}</p>
                    <a
                      href={result.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-blue-600 mt-1 flex items-center gap-1 hover:underline"
                    >
                      <ExternalLink className="w-3 h-3" />
                      {result.url.substring(0, 50)}...
                    </a>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 模态框 */}
      {showModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-md" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800">
                {editingEngine ? '编辑搜索引擎' : '添加搜索引擎'}
              </h3>
              <button
                onClick={() => setShowModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 space-y-3">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">名称</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder="搜索引擎名称"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">适配器类型</label>
                <select
                  value={formData.adapter_type}
                  onChange={(e) => setFormData({ ...formData, adapter_type: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                >
                  <option value="bing">Bing</option>
                  <option value="google">Google</option>
                  <option value="custom">自定义</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
                <input
                  type="password"
                  value={formData.api_key}
                  onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder="API Key"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">API URL</label>
                <input
                  type="text"
                  value={formData.api_url}
                  onChange={(e) => setFormData({ ...formData, api_url: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                  placeholder="可选，自定义API地址"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="search-enabled"
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  className="w-4 h-4 text-blue-600 rounded"
                />
                <label htmlFor="search-enabled" className="text-sm text-gray-700">启用</label>
              </div>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200">
              <button
                onClick={() => setShowModal(false)}
                className="px-4 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={saveEngine}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SearchPanel;
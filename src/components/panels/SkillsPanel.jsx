import { useState, useEffect } from 'react';
import { Wand2, Plus, Play, Edit2, Trash2, X, Save, CheckCircle } from 'lucide-react';

function SkillsPanel() {
  const [skills, setSkills] = useState([]);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [showEditorModal, setShowEditorModal] = useState(false);
  const [showExecuteModal, setShowExecuteModal] = useState(false);
  const [editingSkill, setEditingSkill] = useState(null);
  const [executingSkill, setExecutingSkill] = useState(null);
  const [executeParams, setExecuteParams] = useState({});
  const [newSkill, setNewSkill] = useState({
    name: '',
    description: '',
    skill_type: 'generation',
    executor: 'llm',
    enabled: true,
    icon: 'fas fa-cog',
    prompt_template: '请处理以下内容：\n{content}',
    script: '',
    tags: []
  });
  const [executeResult, setExecuteResult] = useState(null);

  useEffect(() => {
    loadSkills();
  }, []);

  const loadSkills = async () => {
    try {
      const response = await fetch('/api/skills');
      const result = await response.json();
      if (result.skills) {
        setSkills(result.skills);
      }
    } catch (error) {
      console.error('加载Skills失败:', error);
    }
  };

  const openConfigModal = () => {
    setShowConfigModal(true);
  };

  const openEditorModal = (skill = null) => {
    if (skill) {
      setEditingSkill(skill);
      setNewSkill({
        name: skill.name,
        description: skill.description || '',
        skill_type: skill.skill_type || 'generation',
        executor: skill.executor || 'llm',
        enabled: skill.enabled !== false,
        icon: skill.icon || 'fas fa-cog',
        prompt_template: skill.prompt_template || '',
        script: skill.script || '',
        tags: skill.tags || []
      });
    } else {
      setEditingSkill(null);
      setNewSkill({
        name: '',
        description: '',
        skill_type: 'generation',
        executor: 'llm',
        enabled: true,
        icon: 'fas fa-cog',
        prompt_template: '请处理以下内容：\n{content}',
        script: '',
        tags: []
      });
    }
    setShowEditorModal(true);
  };

  const openExecuteModal = async (skillId) => {
    try {
      const response = await fetch(`/api/skills/${skillId}`);
      const result = await response.json();
      if (result.skill) {
        setExecutingSkill(result.skill);
        setExecuteParams({});
        if (result.skill.parameters) {
          result.skill.parameters.forEach(param => {
            setExecuteParams(prev => ({
              ...prev,
              [param.name]: param.default !== null ? param.default : ''
            }));
          });
        }
        setShowExecuteModal(true);
      }
    } catch (error) {
      console.error('获取Skill失败:', error);
    }
  };

  const saveSkill = async () => {
    if (!newSkill.name.trim()) {
      alert('请输入Skill名称');
      return;
    }
    if (newSkill.executor === 'llm' && !newSkill.prompt_template.trim()) {
      alert('选择"AI模型"执行器时必须填写提示模板');
      return;
    }
    if (newSkill.executor === 'script' && !newSkill.script.trim()) {
      alert('选择"脚本"执行器时必须填写脚本内容');
      return;
    }
    try {
      const url = editingSkill 
        ? `/api/skills/${editingSkill.id}` 
        : '/api/skills';
      const method = editingSkill ? 'PUT' : 'POST';
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...newSkill,
          tags: newSkill.tags.split(',').map(t => t.trim()).filter(t => t)
        })
      });
      const result = await response.json();
      if (result.status === 'success') {
        loadSkills();
        setShowEditorModal(false);
      } else {
        alert(result.message || '保存失败');
      }
    } catch (error) {
      console.error('保存失败:', error);
    }
  };

  const deleteSkill = async (skillId) => {
    if (!confirm('确定要删除此Skill?')) return;
    try {
      const response = await fetch(`/api/skills/${skillId}`, {
        method: 'DELETE'
      });
      const result = await response.json();
      if (result.status === 'success') {
        loadSkills();
        setShowEditorModal(false);
      } else {
        alert(result.message || '删除失败');
      }
    } catch (error) {
      console.error('删除失败:', error);
    }
  };

  const executeSkill = async () => {
    try {
      const response = await fetch(`/api/skills/${executingSkill.id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ params: executeParams })
      });
      const result = await response.json();
      if (result.result?.success) {
        setExecuteResult(result.result);
      } else {
        alert('执行失败: ' + (result.result?.error || result.message || '未知错误'));
      }
    } catch (error) {
      alert('执行失败: ' + error.message);
    }
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 工具栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <Wand2 className="w-5 h-5 text-indigo-600" />
          <span className="font-semibold text-gray-800">Skills 管理</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={openConfigModal}
            className="flex items-center gap-1 px-3 py-1.5 text-gray-600 bg-white border border-gray-200 rounded-lg text-sm hover:bg-gray-50"
          >
            <Edit2 className="w-4 h-4" /> 配置
          </button>
          <button
            onClick={() => openEditorModal()}
            className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
          >
            <Plus className="w-4 h-4" /> 新建Skill
          </button>
        </div>
      </div>

      {/* Skills列表 */}
      <div className="flex-1 p-4 overflow-auto">
        {skills.length === 0 ? (
          <div className="text-center text-gray-400 py-8">
            <Wand2 className="w-12 h-12 mx-auto mb-3" />
            <p>暂无Skills</p>
            <p className="text-sm mt-1">点击上方按钮创建新Skill</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {skills.map((skill) => (
              <div
                key={skill.id}
                className={`border rounded-lg p-3 transition-colors ${
                  skill.enabled 
                    ? 'border-gray-200 hover:border-indigo-300' 
                    : 'border-gray-200 opacity-50'
                }`}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{skill.icon ? '' : '⚙️'}</span>
                    <span className="font-medium text-gray-800">{skill.name}</span>
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      skill.enabled 
                        ? 'bg-green-100 text-green-600' 
                        : 'bg-gray-100 text-gray-500'
                    }`}>
                      {skill.enabled ? '启用' : '禁用'}
                    </span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => openExecuteModal(skill.id)}
                      className="p-1.5 text-green-600 hover:bg-green-50 rounded"
                      title="执行"
                    >
                      <Play className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => openEditorModal(skill)}
                      className="p-1.5 text-gray-600 hover:bg-gray-100 rounded"
                      title="编辑"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
                <div className="text-sm text-gray-500 mb-2">{skill.description}</div>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 bg-blue-100 text-blue-600 rounded text-xs">
                    {skill.skill_type}
                  </span>
                  <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs">
                    {skill.executor}
                  </span>
                  {skill.tags && skill.tags.slice(0, 3).map((tag, index) => (
                    <span key={index} className="px-2 py-0.5 bg-purple-100 text-purple-600 rounded text-xs">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 配置模态框 */}
      {showConfigModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-4xl max-h-[80vh]" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Wand2 className="w-5 h-5" /> Skill 配置
              </h3>
              <button
                onClick={() => setShowConfigModal(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex max-h-[calc(80vh-80px)]">
              <div className="w-1/3 border-r border-gray-200 overflow-auto">
                <div className="p-2">
                  {skills.map((skill) => (
                    <div
                      key={skill.id}
                      onClick={() => openEditorModal(skill)}
                      className={`p-2 rounded-lg cursor-pointer transition-colors ${
                        skill.enabled ? '' : 'opacity-50'
                      } ${editingSkill?.id === skill.id ? 'bg-blue-50' : 'hover:bg-gray-50'}`}
                    >
                      <div className="flex items-center gap-2">
                        <span>{skill.icon ? '' : '⚙️'}</span>
                        <span className="text-sm font-medium">{skill.name}</span>
                        <span className={`px-1.5 py-0.5 rounded text-xs ml-auto ${
                          skill.enabled ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-500'
                        }`}>
                          {skill.enabled ? '启用' : '禁用'}
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {skill.executor} · {skill.skill_type}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex-1 p-4">
                {editingSkill ? (
                  <div className="space-y-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">名称</label>
                      <input
                        type="text"
                        value={newSkill.name}
                        onChange={(e) => setNewSkill({ ...newSkill, name: e.target.value })}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">描述</label>
                      <textarea
                        value={newSkill.description}
                        onChange={(e) => setNewSkill({ ...newSkill, description: e.target.value })}
                        rows={2}
                        className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                      />
                    </div>
                    <div className="flex gap-3">
                      <div className="flex-1">
                        <label className="block text-sm font-medium text-gray-700 mb-1">类型</label>
                        <select
                          value={newSkill.skill_type}
                          onChange={(e) => setNewSkill({ ...newSkill, skill_type: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                        >
                          <option value="search">搜索</option>
                          <option value="analysis">分析</option>
                          <option value="generation">生成</option>
                          <option value="transform">转换</option>
                          <option value="validation">验证</option>
                          <option value="custom">自定义</option>
                        </select>
                      </div>
                      <div className="flex-1">
                        <label className="block text-sm font-medium text-gray-700 mb-1">执行器</label>
                        <select
                          value={newSkill.executor}
                          onChange={(e) => setNewSkill({ ...newSkill, executor: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                        >
                          <option value="search">搜索引擎</option>
                          <option value="llm">AI模型</option>
                          <option value="script">脚本</option>
                          <option value="api">API调用</option>
                        </select>
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={newSkill.enabled}
                        onChange={(e) => setNewSkill({ ...newSkill, enabled: e.target.checked })}
                        className="w-4 h-4 text-blue-600 rounded"
                      />
                      <label className="text-sm text-gray-700">启用</label>
                    </div>
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => deleteSkill(editingSkill.id)}
                        className="px-3 py-1.5 text-red-600 border border-red-200 rounded-lg text-sm hover:bg-red-50"
                      >
                        <Trash2 className="w-4 h-4 inline mr-1" /> 删除
                      </button>
                      <button
                        onClick={saveSkill}
                        className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
                      >
                        <Save className="w-4 h-4 inline mr-1" /> 保存
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="text-center text-gray-400 py-12">
                    <Wand2 className="w-12 h-12 mx-auto mb-3" />
                    <p>点击左侧列表中的Skill进行编辑</p>
                    <p className="text-sm mt-1">或点击"新建"创建新的Skill</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 编辑器模态框 */}
      {showEditorModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-4xl max-h-[90vh]" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Wand2 className="w-5 h-5" /> {editingSkill ? '编辑Skill' : '新建Skill'}
              </h3>
              <div className="flex items-center gap-2">
                {editingSkill && (
                  <button
                    onClick={() => deleteSkill(editingSkill.id)}
                    className="px-3 py-1.5 text-red-600 border border-red-200 rounded-lg text-sm hover:bg-red-50"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                )}
                <button
                  onClick={saveSkill}
                  className="px-3 py-1.5 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
                >
                  <Save className="w-4 h-4 inline mr-1" /> 保存
                </button>
                <button
                  onClick={() => setShowEditorModal(false)}
                  className="px-3 py-1.5 text-gray-600 bg-gray-100 rounded-lg text-sm"
                >
                  <X className="w-4 h-4" /> 关闭
                </button>
              </div>
            </div>
            <div className="p-4 max-h-[calc(90vh-120px)] overflow-auto">
              <div className="grid grid-cols-3 gap-4 mb-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">名称 <span className="text-red-500">*</span></label>
                  <input
                    type="text"
                    value={newSkill.name}
                    onChange={(e) => setNewSkill({ ...newSkill, name: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                    placeholder="Skill名称"
                  />
                </div>
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-gray-700 mb-1">描述</label>
                  <input
                    type="text"
                    value={newSkill.description}
                    onChange={(e) => setNewSkill({ ...newSkill, description: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                    placeholder="描述这个Skill的功能..."
                  />
                </div>
              </div>
              <div className="flex gap-4 mb-4">
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1">类型</label>
                  <select
                    value={newSkill.skill_type}
                    onChange={(e) => setNewSkill({ ...newSkill, skill_type: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                  >
                    <option value="search">搜索</option>
                    <option value="analysis">分析</option>
                    <option value="generation">生成</option>
                    <option value="transform">转换</option>
                    <option value="validation">验证</option>
                    <option value="custom">自定义</option>
                  </select>
                </div>
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1">执行器</label>
                  <select
                    value={newSkill.executor}
                    onChange={(e) => setNewSkill({ ...newSkill, executor: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                  >
                    <option value="search">搜索引擎</option>
                    <option value="llm">AI模型</option>
                    <option value="script">脚本</option>
                    <option value="api">API调用</option>
                  </select>
                </div>
                <div className="flex-1">
                  <label className="block text-sm font-medium text-gray-700 mb-1">图标 (FontAwesome)</label>
                  <input
                    type="text"
                    value={newSkill.icon}
                    onChange={(e) => setNewSkill({ ...newSkill, icon: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                    placeholder="fas fa-cog"
                  />
                </div>
              </div>
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-1">提示模板 (使用{变量名}作为占位符)</label>
                <textarea
                  value={newSkill.prompt_template}
                  onChange={(e) => setNewSkill({ ...newSkill, prompt_template: e.target.value })}
                  rows={4}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono"
                  placeholder="请处理以下内容：\n{content}"
                />
              </div>
              {newSkill.executor === 'script' && (
                <div className="mb-4">
                  <label className="block text-sm font-medium text-gray-700 mb-1">脚本内容 (Python)</label>
                  <textarea
                    value={newSkill.script}
                    onChange={(e) => setNewSkill({ ...newSkill, script: e.target.value })}
                    rows={6}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono"
                    placeholder="def execute(input_data):\n    return {'result': '处理完成'}"
                  />
                </div>
              )}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">标签 (用逗号分隔)</label>
                <input
                  type="text"
                  value={newSkill.tags.join(', ')}
                  onChange={(e) => setNewSkill({ ...newSkill, tags: e.target.value.split(',').map(t => t.trim()).filter(t => t) })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                  placeholder="标签1, 标签2"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 执行模态框 */}
      {showExecuteModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Play className="w-5 h-5" /> 执行: {executingSkill?.name}
              </h3>
              <button
                onClick={() => { setShowExecuteModal(false); setExecuteResult(null); }}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4">
              {executingSkill?.parameters && executingSkill.parameters.length > 0 ? (
                <div className="space-y-3">
                  {executingSkill.parameters.map((param) => (
                    <div key={param.name}>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        {param.description || param.name}
                        {param.required && <span className="text-red-500">*</span>}
                      </label>
                      {param.type === 'boolean' ? (
                        <input
                          type="checkbox"
                          checked={executeParams[param.name] || false}
                          onChange={(e) => setExecuteParams({ ...executeParams, [param.name]: e.target.checked })}
                          className="w-4 h-4 text-blue-600 rounded"
                        />
                      ) : param.type === 'textarea' ? (
                        <textarea
                          value={executeParams[param.name] || ''}
                          onChange={(e) => setExecuteParams({ ...executeParams, [param.name]: e.target.value })}
                          rows={4}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                        />
                      ) : param.type === 'select' && param.options ? (
                        <select
                          value={executeParams[param.name] || ''}
                          onChange={(e) => setExecuteParams({ ...executeParams, [param.name]: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                        >
                          {param.options.map((opt) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type={param.type === 'number' ? 'number' : 'text'}
                          value={executeParams[param.name] || ''}
                          onChange={(e) => setExecuteParams({ ...executeParams, [param.name]: e.target.value })}
                          className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm"
                        />
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center text-gray-400 py-4">
                  <p>此Skill没有可配置参数</p>
                  <p className="text-sm mt-1">直接点击"执行"按钮即可运行</p>
                </div>
              )}
              {executeResult && (
                <div className="mt-4 p-4 bg-green-50 rounded-lg">
                  <div className="flex items-center gap-2 mb-2">
                    <CheckCircle className="w-5 h-5 text-green-600" />
                    <span className="font-medium text-green-700">执行成功</span>
                  </div>
                  {executeResult.execution_time && (
                    <div className="text-sm text-gray-600 mb-2">
                      执行时间: {executeResult.execution_time.toFixed(2)}秒
                      {' | '} Token: {executeResult.tokens_used || 0}
                    </div>
                  )}
                  <div className="text-sm text-gray-700 whitespace-pre-wrap font-mono">
                    {executeResult.output || '无输出'}
                  </div>
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200">
              <button
                onClick={() => { setShowExecuteModal(false); setExecuteResult(null); }}
                className="px-4 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50"
              >
                取消
              </button>
              <button
                onClick={executeSkill}
                disabled={!!executeResult}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                <Play className="w-4 h-4 inline mr-1" /> 执行
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SkillsPanel;
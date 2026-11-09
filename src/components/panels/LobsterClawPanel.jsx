import { useState, useEffect, useRef } from 'react';
import { Send, Paperclip, X, Download, RefreshCw, FileText, Bot, History, Trash2, Clock, Calendar, Bell, Bookmark, MessageSquare, Code, Plus, Edit, Play, Save, ChevronRight } from 'lucide-react';
import { marked } from 'marked';

function LobsterClawPanel() {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState('');
  const [models, setModels] = useState([]);
  const [attachments, setAttachments] = useState([]);
  const [showMemoryDialog, setShowMemoryDialog] = useState(false);
  const [showScheduleDialog, setShowScheduleDialog] = useState(false);
  const [showSessionDialog, setShowSessionDialog] = useState(false);
  const [showScriptDialog, setShowScriptDialog] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [memories, setMemories] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [activeTab, setActiveTab] = useState('chat');
  const [scripts, setScripts] = useState([]);
  const [editingScript, setEditingScript] = useState(null);
  const [newScript, setNewScript] = useState({ name: '', description: '', code: '' });
  const [scriptFilter, setScriptFilter] = useState('');

  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadModels();
    loadAttachments();
    loadMemories();
    loadSchedules();
    loadSessions();
    scrollToBottom();
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const loadModels = async () => {
    try {
      const response = await fetch('/api/models');
      const modelList = await response.json();
      setModels(modelList);
      if (modelList.length > 0 && !selectedModel) {
        setSelectedModel(modelList[0].model_name || modelList[0].name || '');
      }
    } catch (error) {
      console.error('加载模型失败:', error);
    }
  };

  const loadAttachments = async () => {
    try {
      const response = await fetch('/api/attachments');
      const files = await response.json();
      setAttachments(files);
    } catch (error) {
      console.error('加载附件失败:', error);
    }
  };

  const loadMemories = async () => {
    try {
      const response = await fetch('/api/memory');
      const data = await response.json();
      setMemories(data.memories || []);
    } catch (error) {
      console.error('加载记忆失败:', error);
    }
  };

  const loadSchedules = async () => {
    try {
      const response = await fetch('/api/schedules');
      const data = await response.json();
      setSchedules(data.schedules || []);
    } catch (error) {
      console.error('加载定时任务失败:', error);
    }
  };

  const loadSessions = async () => {
    try {
      const response = await fetch('/api/lobster-claw/sessions');
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (error) {
      console.error('加载会话失败:', error);
    }
  };

  const loadScripts = async () => {
    try {
      const response = await fetch('/api/scripts/list');
      const result = await response.json();
      if (result.success) {
        setScripts(result.scripts);
      }
    } catch (error) {
      console.error('加载脚本失败:', error);
    }
  };

  const handleCreateScript = async () => {
    try {
      const response = await fetch('/api/scripts/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newScript),
      });
      const result = await response.json();
      if (result.success) {
        loadScripts();
        setNewScript({ name: '', description: '', code: '' });
        setShowScriptDialog(false);
        setEditingScript(null);
      }
    } catch (error) {
      console.error('创建脚本失败:', error);
    }
  };

  const handleUpdateScript = async () => {
    if (!editingScript) return;
    try {
      const response = await fetch('/api/scripts/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editingScript),
      });
      const result = await response.json();
      if (result.success) {
        loadScripts();
        setEditingScript(null);
        setShowScriptDialog(false);
      }
    } catch (error) {
      console.error('更新脚本失败:', error);
    }
  };

  const handleDeleteScript = async (scriptId) => {
    if (!confirm('确定删除此脚本？')) return;
    try {
      const response = await fetch('/api/scripts/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_id: scriptId }),
      });
      const result = await response.json();
      if (result.success) {
        loadScripts();
      }
    } catch (error) {
      console.error('删除脚本失败:', error);
    }
  };

  const handleRunScript = async (scriptId) => {
    try {
      const response = await fetch('/api/scripts/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_id: scriptId }),
      });
      const result = await response.json();
      if (result.success) {
        alert('脚本执行成功');
      } else {
        alert(`脚本执行失败: ${result.message}`);
      }
    } catch (error) {
      console.error('执行脚本失败:', error);
    }
  };

  const highlightPython = (code) => {
    if (!code) return '';
    const keywords = ['def', 'class', 'if', 'elif', 'else', 'for', 'while', 'return', 'import', 'from', 'as', 'try', 'except', 'finally', 'with', 'lambda', 'yield', 'async', 'await', 'True', 'False', 'None'];
    let result = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    
    keywords.forEach(keyword => {
      const regex = new RegExp(`\\b(${keyword})\\b`, 'g');
      result = result.replace(regex, '<span class="text-purple-600 font-medium">$1</span>');
    });
    
    result = result.replace(/("#.*")|('.*')/g, '<span class="text-green-600">$1$2</span>');
    result = result.replace(/(\d+)/g, '<span class="text-orange-600">$1</span>');
    
    return result;
  };

  const handleFileUpload = async (e) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    
    for (const file of files) {
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const response = await fetch('/api/attachments/upload', {
          method: 'POST',
          body: formData
        });
        const result = await response.json();
        if (result.status === 'success') {
          setMessages(prev => [...prev, {
            role: 'system',
            content: `附件上传成功: ${result.filename}`
          }]);
        } else {
          setMessages(prev => [...prev, {
            role: 'system',
            content: `附件上传失败: ${result.message}`
          }]);
        }
      } catch (error) {
        setMessages(prev => [...prev, {
          role: 'system',
          content: `上传失败: ${error.message}`
        }]);
      }
    }
    await loadAttachments();
    e.target.value = '';
  };

  const removeAttachment = async (filename) => {
    try {
      const response = await fetch(`/api/attachments/${filename}`, { method: 'DELETE' });
      const result = await response.json();
      if (result.status === 'success') {
        await loadAttachments();
      }
    } catch (error) {
      console.error('删除附件失败:', error);
    }
  };

  const handleSendMessage = async () => {
    const message = inputMessage.trim();
    if (!message && attachments.length === 0) {
      return;
    }

    setIsLoading(true);
    setMessages(prev => [...prev, {
      role: 'user',
      content: message,
      attachments: [...attachments]
    }]);
    setInputMessage('');

    try {
      const response = await fetch('/api/lobster-claw/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          model_name: selectedModel,
          files: attachments.map(f => ({ filename: f }))
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let responseContent = '';

      let modelName = '';
      let tokenStats = null;
      let timestamp = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.substring(6));
              if (data.content) {
                responseContent += data.content;
                setMessages(prev => {
                  const lastIndex = prev.length - 1;
                  if (prev[lastIndex]?.role === 'assistant') {
                    return [
                      ...prev.slice(0, lastIndex),
                      { ...prev[lastIndex], content: responseContent }
                    ];
                  } else {
                    return [...prev, { role: 'assistant', content: responseContent }];
                  }
                });
              }
              if (data.model_name) {
                modelName = data.model_name;
              }
              if (data.token_stats) {
                tokenStats = data.token_stats;
              }
              if (data.timestamp) {
                timestamp = data.timestamp;
              }
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }

      if (responseContent) {
        setMessages(prev => {
          const lastIndex = prev.length - 1;
          if (prev[lastIndex]?.role === 'assistant') {
            return [
              ...prev.slice(0, lastIndex),
              { 
                ...prev[lastIndex], 
                model_name: modelName || selectedModel,
                token_stats: tokenStats,
                timestamp: timestamp || new Date().toISOString()
              }
            ];
          }
          return prev;
        });
      }
    } catch (error) {
      setMessages(prev => [...prev, {
        role: 'system',
        content: `发送失败: ${error.message}`
      }]);
    } finally {
      setIsLoading(false);
      setAttachments([]);
      await loadAttachments();
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const clearMessages = () => {
    if (!confirm('确定要清空所有消息吗？')) return;
    setMessages([]);
  };

  const exportMessages = () => {
    const content = messages.map(msg => {
      const role = msg.role === 'user' ? '用户' : msg.role === 'assistant' ? '助手' : '系统';
      return `${role}: ${msg.content}`;
    }).join('\n\n');
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `chat_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  const selectSession = async (sessionId) => {
    try {
      const response = await fetch(`/api/lobster-claw/sessions/${sessionId}`);
      const data = await response.json();
      if (data.messages) {
        setMessages(data.messages);
      }
      setShowSessionDialog(false);
    } catch (error) {
      console.error('加载会话失败:', error);
    }
  };

  const deleteSession = async (sessionId) => {
    if (!confirm('确定要删除这个会话吗？')) return;
    try {
      const response = await fetch(`/api/lobster-claw/sessions/${sessionId}`, { method: 'DELETE' });
      const result = await response.json();
      if (result.status === 'success') {
        await loadSessions();
        if (currentSessionId === sessionId) {
          setCurrentSessionId(null);
          setMessages([]);
        }
      }
    } catch (error) {
      console.error('删除会话失败:', error);
    }
  };

  const createNewSession = async () => {
    try {
      const response = await fetch('/api/lobster-claw/sessions', { method: 'POST' });
      const result = await response.json();
      if (result.status === 'success') {
        setCurrentSessionId(result.session_id);
        setMessages([]);
        setInputMessage('');
        setAttachments([]);
        await loadSessions();
      }
    } catch (error) {
      console.error('创建会话失败:', error);
    }
  };

  const addMemory = async () => {
    const content = prompt('请输入记忆内容:');
    if (!content) return;
    try {
      const response = await fetch('/api/memory', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });
      const result = await response.json();
      if (result.status === 'success') {
        await loadMemories();
      }
    } catch (error) {
      console.error('添加记忆失败:', error);
    }
  };

  const deleteMemory = async (memoryId) => {
    if (!confirm('确定要删除这个记忆吗？')) return;
    try {
      const response = await fetch(`/api/memory/${memoryId}`, { method: 'DELETE' });
      const result = await response.json();
      if (result.status === 'success') {
        await loadMemories();
      }
    } catch (error) {
      console.error('删除记忆失败:', error);
    }
  };

  const addSchedule = async () => {
    const name = prompt('请输入定时任务名称:');
    const cron = prompt('请输入Cron表达式:');
    const action = prompt('请输入执行动作:');
    if (!name || !cron || !action) return;
    
    try {
      const response = await fetch('/api/schedules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, cron, action })
      });
      const result = await response.json();
      if (result.status === 'success') {
        await loadSchedules();
      }
    } catch (error) {
      console.error('添加定时任务失败:', error);
    }
  };

  const toggleSchedule = async (scheduleId, enabled) => {
    try {
      const response = await fetch(`/api/schedules/${scheduleId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !enabled })
      });
      const result = await response.json();
      if (result.status === 'success') {
        await loadSchedules();
      }
    } catch (error) {
      console.error('更新定时任务失败:', error);
    }
  };

  const deleteSchedule = async (scheduleId) => {
    if (!confirm('确定要删除这个定时任务吗？')) return;
    try {
      const response = await fetch(`/api/schedules/${scheduleId}`, { method: 'DELETE' });
      const result = await response.json();
      if (result.status === 'success') {
        await loadSchedules();
      }
    } catch (error) {
      console.error('删除定时任务失败:', error);
    }
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 顶部工具栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-4">
          {/* 标签页 */}
          <div className="flex border border-gray-200 rounded-lg">
            <button 
              onClick={() => setActiveTab('chat')}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-l-lg transition-colors ${
                activeTab === 'chat' ? 'bg-gray-100 text-gray-800' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <MessageSquare className="w-4 h-4" /> 聊天
            </button>
            <button 
              onClick={() => setActiveTab('session')}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-r-lg transition-colors ${
                activeTab === 'session' ? 'bg-gray-100 text-gray-800' : 'text-gray-500 hover:text-gray-700'
              }`}
            >
              <History className="w-4 h-4" /> 会话记录
            </button>
          </div>

          {/* 模型选择 */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">模型:</span>
            <select 
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="px-3 py-2 border border-gray-200 rounded-lg text-sm"
            >
              {models.map((model, index) => (
                <option key={index} value={model.model_name || model.name}>
                  {model.model_name || model.name} ({model.api_type || 'unknown'})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={createNewSession} className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
            <MessageSquare className="w-4 h-4" /> 新建会话
          </button>
          <button onClick={() => { loadScripts(); setShowScriptDialog(true); }} className="flex items-center gap-2 px-3 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
            <Code className="w-4 h-4" /> 脚本管理
          </button>
          <button onClick={() => setShowMemoryDialog(true)} className="flex items-center gap-2 px-3 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
            <Bookmark className="w-4 h-4" /> 记忆管理
          </button>
          <button onClick={() => setShowScheduleDialog(true)} className="flex items-center gap-2 px-3 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
            <Clock className="w-4 h-4" /> 定时任务
          </button>
          <button onClick={clearMessages} className="flex items-center gap-2 px-3 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
            <Trash2 className="w-4 h-4" /> 清空消息
          </button>
          <button onClick={exportMessages} className="flex items-center gap-2 px-3 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
            <Download className="w-4 h-4" /> 导出
          </button>
        </div>
      </div>

      {/* 主内容区域 */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'chat' ? (
          /* 聊天区域 */
          <div className="h-full flex flex-col">
            {/* 消息列表 */}
            <div className="flex-1 overflow-auto p-4 space-y-4">
              {messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-gray-400">
                  <Bot className="w-16 h-16 mb-4" />
                  <p className="text-lg">龙虾Claw</p>
                  <p className="text-sm">欢迎使用，我可以帮助您处理各种任务</p>
                  <div className="mt-6 flex flex-wrap justify-center gap-2">
                    <span className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">上传文件分析</span>
                    <span className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">代码生成</span>
                    <span className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">文档处理</span>
                    <span className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">数据分析</span>
                  </div>
                </div>
              ) : (
                messages.map((msg, index) => (
                  <div 
                    key={index} 
                    className={`flex flex-col ${msg.role === 'user' ? 'items-end' : msg.role === 'assistant' ? 'items-start' : 'items-center'} mb-4`}
                  >
                    <div className={`flex ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'} max-w-[70%]`}>
                      <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
                        msg.role === 'user' ? 'bg-blue-600' :
                        msg.role === 'assistant' ? 'bg-green-500' :
                        'bg-gray-400'
                      } ${msg.role === 'user' ? 'ml-2' : 'mr-2'}`}>
                        {msg.role === 'user' ? (
                          <span className="text-white text-xs">人</span>
                        ) : msg.role === 'assistant' ? (
                          <Bot className="w-4 h-4 text-white" />
                        ) : (
                          <span className="text-white text-xs">系</span>
                        )}
                      </div>
                      <div className={`${
                        msg.role === 'user' ? 'bg-blue-600 text-white' :
                        msg.role === 'assistant' ? 'bg-gray-100 text-gray-800' :
                        'bg-yellow-50 text-yellow-800'
                      } rounded-xl px-4 py-3 shadow-sm`}>
                        {msg.role === 'user' && msg.attachments && msg.attachments.length > 0 && (
                          <div className="flex flex-wrap gap-2 mb-2">
                            {msg.attachments.map((file, i) => (
                              <span key={i} className="inline-flex items-center gap-1 px-2 py-1 bg-blue-500 rounded text-xs">
                                <FileText className="w-3 h-3" /> {file}
                              </span>
                            ))}
                          </div>
                        )}
                        {msg.role === 'assistant' ? (
                          <div 
                            className="text-sm markdown-content" 
                            dangerouslySetInnerHTML={{ __html: marked.parse(msg.content) }}
                          />
                        ) : (
                          <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                        )}
                      </div>
                    </div>
                    {msg.role === 'assistant' && (msg.model_name || msg.token_stats || msg.timestamp) && (
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                        {msg.model_name && <span>模型: {msg.model_name}</span>}
                        {msg.token_stats && (
                          <span>
                            输入 {msg.token_stats.prompt_tokens || 0} → 输出 {msg.token_stats.completion_tokens || 0} tokens
                            {msg.token_stats.tokens_per_second && (
                              <span className="ml-1">({msg.token_stats.tokens_per_second.toFixed(1)}/s)</span>
                            )}
                          </span>
                        )}
                        {msg.timestamp && <span>{new Date(msg.timestamp).toLocaleString('zh-CN')}</span>}
                      </div>
                    )}
                  </div>
                ))
              )}
              <div ref={messagesEndRef}></div>
            </div>

            {/* 附件列表 */}
            {attachments.length > 0 && (
              <div className="px-4 py-2 bg-blue-50 border-t border-blue-100">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs text-blue-600 font-medium">已选择附件:</span>
                  {attachments.map((file, index) => (
                    <span key={index} className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-600 rounded-full text-xs">
                      <FileText className="w-3 h-3" />
                      {file}
                      <button onClick={() => removeAttachment(file)} className="hover:text-red-600">
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* 输入区域 */}
            <div className="px-4 py-3 border-t border-gray-200">
              <div className="flex items-end gap-3">
                <div className="flex-1">
                  <textarea
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyPress={handleKeyPress}
                    placeholder="输入消息..."
                    className="w-full px-4 py-3 border border-gray-200 rounded-xl resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-sm"
                    rows={3}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <label className="p-3 border border-gray-200 rounded-xl cursor-pointer hover:bg-gray-50">
                    <Paperclip className="w-5 h-5 text-gray-500" />
                    <input type="file" multiple className="hidden" onChange={handleFileUpload} />
                  </label>
                  <button 
                    onClick={handleSendMessage}
                    disabled={isLoading || (!inputMessage.trim() && attachments.length === 0)}
                    className="p-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isLoading ? (
                      <RefreshCw className="w-5 h-5 animate-spin" />
                    ) : (
                      <Send className="w-5 h-5" />
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* 会话记录区域 */
          <div className="h-full p-4 overflow-auto">
            {sessions.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <History className="w-16 h-16 mb-4" />
                <p>暂无会话记录</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {sessions.map((session, index) => (
                  <div 
                    key={index} 
                    className="p-4 border border-gray-200 rounded-xl hover:border-blue-400 hover:shadow-md transition-all cursor-pointer"
                    onClick={() => selectSession(session.id)}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-gray-800">{session.title || '未命名会话'}</span>
                      <button 
                        onClick={(e) => { e.stopPropagation(); deleteSession(session.id); }}
                        className="text-gray-400 hover:text-red-600"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                    <div className="text-sm text-gray-500 mb-2">
                      {session.message_count || 0} 条消息
                    </div>
                    <div className="text-xs text-gray-400">
                      {new Date(session.created_at).toLocaleString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 记忆管理对话框 */}
      {showMemoryDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Bookmark className="w-5 h-5" /> 记忆管理
              </h3>
              <button onClick={() => setShowMemoryDialog(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 max-h-96 overflow-auto">
              {memories.length === 0 ? (
                <p className="text-gray-400 text-center">暂无记忆</p>
              ) : (
                <div className="space-y-2">
                  {memories.map((memory, index) => (
                    <div key={index} className="flex items-start gap-2 p-3 bg-gray-50 rounded-lg">
                      <div className="flex-1">
                        <p className="text-sm text-gray-800">{memory.content}</p>
                        <p className="text-xs text-gray-400 mt-1">
                          {new Date(memory.created_at).toLocaleString()}
                        </p>
                      </div>
                      <button 
                        onClick={() => deleteMemory(memory.id)}
                        className="text-gray-400 hover:text-red-600"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200">
              <button onClick={() => setShowMemoryDialog(false)} className="px-4 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
                关闭
              </button>
              <button onClick={addMemory} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                添加记忆
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 定时任务对话框 */}
      {showScheduleDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-lg" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Clock className="w-5 h-5" /> 定时任务
              </h3>
              <button onClick={() => setShowScheduleDialog(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 max-h-96 overflow-auto">
              {schedules.length === 0 ? (
                <p className="text-gray-400 text-center">暂无定时任务</p>
              ) : (
                <div className="space-y-2">
                  {schedules.map((schedule, index) => (
                    <div key={index} className="flex items-center gap-3 p-3 bg-gray-50 rounded-lg">
                      <button 
                        onClick={() => toggleSchedule(schedule.id, schedule.enabled)}
                        className={`w-10 h-10 rounded-full flex items-center justify-center ${
                          schedule.enabled ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400'
                        }`}
                      >
                        <Bell className="w-5 h-5" />
                      </button>
                      <div className="flex-1">
                        <p className="font-medium text-gray-800">{schedule.name}</p>
                        <p className="text-xs text-gray-500">{schedule.cron}</p>
                      </div>
                      <button 
                        onClick={() => deleteSchedule(schedule.id)}
                        className="text-gray-400 hover:text-red-600"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200">
              <button onClick={() => setShowScheduleDialog(false)} className="px-4 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
                关闭
              </button>
              <button onClick={addSchedule} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                添加任务
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 脚本管理对话框 */}
      {showScriptDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Code className="w-5 h-5" /> 脚本管理
              </h3>
              <button onClick={() => { setShowScriptDialog(false); setEditingScript(null); setNewScript({ name: '', description: '', code: '' }); }} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 flex-1 overflow-auto">
              <div className="mb-4">
                <input
                  type="text"
                  value={scriptFilter}
                  onChange={(e) => setScriptFilter(e.target.value)}
                  placeholder="搜索脚本名称或描述..."
                  className="w-full px-4 py-2 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
                />
              </div>
              <div className="flex justify-end mb-4">
                <button
                  onClick={() => { setEditingScript(null); setNewScript({ name: '', description: '', code: '' }); setShowScriptDialog(true); }}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
                >
                  <Plus className="w-5 h-5" />
                  创建脚本
                </button>
              </div>
              <div className="space-y-3">
                {scripts.filter(script =>
                  script.name.toLowerCase().includes(scriptFilter.toLowerCase()) ||
                  script.description.toLowerCase().includes(scriptFilter.toLowerCase())
                ).map((script) => (
                  <div key={script.id} className="bg-gray-50 border border-gray-200 rounded-lg p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <h4 className="font-medium text-gray-800">{script.name}</h4>
                          <span className="px-2 py-0.5 bg-gray-200 text-gray-600 text-xs rounded-full">
                            {script.language || 'Python'}
                          </span>
                        </div>
                        <p className="text-sm text-gray-500 mt-1">{script.description}</p>
                        <pre className="mt-2 p-2 bg-white rounded text-xs overflow-x-auto max-h-24 overflow-y-auto font-mono">
                          <code dangerouslySetInnerHTML={{ __html: highlightPython(script.code.substring(0, 300) + (script.code.length > 300 ? '...' : '')) }} />
                        </pre>
                      </div>
                      <div className="flex flex-col gap-2 ml-4">
                        <button
                          onClick={() => { setEditingScript(script); }}
                          className="p-2 text-gray-500 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
                          title="编辑"
                        >
                          <Edit className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleRunScript(script.id)}
                          className="p-2 text-gray-500 hover:text-green-600 hover:bg-green-50 rounded-lg transition-colors"
                          title="运行"
                        >
                          <Play className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDeleteScript(script.id)}
                          className="p-2 text-gray-500 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                          title="删除"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              {scripts.length === 0 && (
                <p className="text-gray-400 text-center py-8">暂无脚本</p>
              )}
            </div>

            {/* 编辑/创建脚本表单 */}
            {editingScript && (
              <div className="border-t border-gray-200 p-4">
                <h4 className="font-medium text-gray-800 mb-3">编辑脚本</h4>
                <div className="space-y-3">
                  <input
                    type="text"
                    value={editingScript.name}
                    onChange={(e) => setEditingScript({ ...editingScript, name: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg"
                    placeholder="脚本名称"
                  />
                  <input
                    type="text"
                    value={editingScript.description}
                    onChange={(e) => setEditingScript({ ...editingScript, description: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg"
                    placeholder="脚本描述"
                  />
                  <textarea
                    value={editingScript.code}
                    onChange={(e) => setEditingScript({ ...editingScript, code: e.target.value })}
                    className="w-full px-3 py-2 border border-gray-200 rounded-lg font-mono text-sm h-32"
                    placeholder="脚本代码"
                  />
                  <div className="flex justify-end gap-2">
                    <button onClick={() => setEditingScript(null)} className="px-4 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
                      取消
                    </button>
                    <button onClick={handleUpdateScript} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                      保存
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 创建脚本弹窗 */}
      {!editingScript && showScriptDialog && newScript.name !== '' && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-4xl max-h-[90vh] flex flex-col" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Plus className="w-5 h-5" /> 创建脚本
              </h3>
              <button onClick={() => { setNewScript({ name: '', description: '', code: '' }); }} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4 flex-1 overflow-auto">
              <div className="space-y-3">
                <input
                  type="text"
                  value={newScript.name}
                  onChange={(e) => setNewScript({ ...newScript, name: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg"
                  placeholder="脚本名称"
                />
                <input
                  type="text"
                  value={newScript.description}
                  onChange={(e) => setNewScript({ ...newScript, description: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg"
                  placeholder="脚本描述"
                />
                <textarea
                  value={newScript.code}
                  onChange={(e) => setNewScript({ ...newScript, code: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg font-mono text-sm h-48"
                  placeholder="脚本代码"
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200">
              <button onClick={() => { setNewScript({ name: '', description: '', code: '' }); }} className="px-4 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
                取消
              </button>
              <button onClick={handleCreateScript} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                创建
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default LobsterClawPanel;
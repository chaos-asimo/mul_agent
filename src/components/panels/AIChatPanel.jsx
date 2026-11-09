import { useState, useEffect, useRef } from 'react';
import { Send, Paperclip, X, Download, RefreshCw, User, Bot, History, Trash2, Smile, Settings } from 'lucide-react';

const ROLES = [
  { id: 'general', name: '通用助手', description: '全能型AI助手', avatar: '🤖' },
  { id: 'code', name: '代码助手', description: '专业的代码生成和调试', avatar: '💻' },
  { id: 'writer', name: '写作助手', description: '文章创作和润色', avatar: '✍️' },
  { id: 'analyst', name: '数据分析', description: '数据处理和分析', avatar: '📊' },
  { id: 'translator', name: '翻译助手', description: '多语言翻译', avatar: '🌐' },
  { id: 'teacher', name: '学习导师', description: '知识讲解和辅导', avatar: '👨‍🏫' },
];

function AIChatPanel() {
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedRole, setSelectedRole] = useState('general');
  const [selectedModel, setSelectedModel] = useState('');
  const [models, setModels] = useState([]);
  const [showRoleSelector, setShowRoleSelector] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const messagesEndRef = useRef(null);

  useEffect(() => {
    loadModels();
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
      const data = await response.json();
      const modelList = data.models || [];
      setModels(modelList);
      if (modelList.length > 0 && !selectedModel) {
        setSelectedModel(modelList[0].name || modelList[0].model_id || '');
      }
    } catch (error) {
      console.error('加载模型失败:', error);
    }
  };

  const handleSendMessage = async () => {
    const message = inputMessage.trim();
    if (!message) return;

    setIsLoading(true);
    setMessages(prev => [...prev, {
      role: 'user',
      content: message
    }]);
    setInputMessage('');

    const role = ROLES.find(r => r.id === selectedRole);
    const systemPrompt = getRolePrompt(role);

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          model: selectedModel,
          system_prompt: systemPrompt,
          history: messages.slice(-10).map(msg => ({
            role: msg.role,
            content: msg.content
          }))
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let responseContent = '';

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
            } catch (e) {
              // 忽略解析错误
            }
          }
        }
      }
    } catch (error) {
      setMessages(prev => [...prev, {
        role: 'system',
        content: `发送失败: ${error.message}`
      }]);
    } finally {
      setIsLoading(false);
    }
  };

  const getRolePrompt = (role) => {
    const prompts = {
      general: '你是一个全能型AI助手，可以回答各种问题，提供帮助和建议。',
      code: '你是一个专业的编程助手。请提供清晰、正确的代码，并附上详细的解释。',
      writer: '你是一个专业的写作助手。请帮助用户创作和润色文章，确保内容流畅、优美。',
      analyst: '你是一个专业的数据分析师。请帮助用户分析数据，提供洞察和建议。',
      translator: '你是一个专业的翻译助手。请准确翻译用户的内容，并保持原意不变。',
      teacher: '你是一个耐心的学习导师。请用通俗易懂的方式讲解知识，帮助用户理解。'
    };
    return prompts[role.id] || prompts.general;
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

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 顶部工具栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-4">
          {/* 角色选择 */}
          <div className="relative">
            <button
              onClick={() => setShowRoleSelector(!showRoleSelector)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              <span>{ROLES.find(r => r.id === selectedRole)?.avatar}</span>
              <span>{ROLES.find(r => r.id === selectedRole)?.name}</span>
            </button>
            
            {showRoleSelector && (
              <div className="absolute top-full left-0 mt-2 w-64 bg-white border border-gray-200 rounded-lg shadow-lg z-10">
                {ROLES.map((role) => (
                  <button
                    key={role.id}
                    onClick={() => {
                      setSelectedRole(role.id);
                      setShowRoleSelector(false);
                    }}
                    className={`w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-50 ${
                      selectedRole === role.id ? 'bg-blue-50' : ''
                    }`}
                  >
                    <span className="text-xl">{role.avatar}</span>
                    <div>
                      <div className="font-medium text-gray-800">{role.name}</div>
                      <div className="text-xs text-gray-500">{role.description}</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
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
                <option key={index} value={model.name || model.model_id}>
                  {model.name || model.model_id} ({model.provider})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button onClick={clearMessages} className="flex items-center gap-2 px-3 py-2 text-red-600 border border-red-200 rounded-lg hover:bg-red-50">
            <Trash2 className="w-4 h-4" /> 清空
          </button>
          <button onClick={exportMessages} className="flex items-center gap-2 px-3 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
            <Download className="w-4 h-4" /> 导出
          </button>
          <button onClick={() => setShowSettings(!showSettings)} className="flex items-center gap-2 px-3 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
            <Settings className="w-4 h-4" /> 设置
          </button>
        </div>
      </div>

      {/* 主内容区域 */}
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <Bot className="w-16 h-16 mb-4" />
            <p className="text-lg font-medium text-gray-600">{ROLES.find(r => r.id === selectedRole)?.name}</p>
            <p className="text-sm">{ROLES.find(r => r.id === selectedRole)?.description}</p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {ROLES.find(r => r.id === selectedRole)?.id === 'general' && (
                <>
                  <span className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">问答对话</span>
                  <span className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">信息查询</span>
                  <span className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">创意生成</span>
                </>
              )}
              {ROLES.find(r => r.id === selectedRole)?.id === 'code' && (
                <>
                  <span className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">代码生成</span>
                  <span className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">Bug修复</span>
                  <span className="px-3 py-1 bg-gray-100 rounded-full text-sm text-gray-600">代码优化</span>
                </>
              )}
            </div>
          </div>
        ) : (
          messages.map((msg, index) => (
            <div 
              key={index} 
              className={`flex ${msg.role === 'user' ? 'justify-end' : msg.role === 'assistant' ? 'justify-start' : 'justify-center'}`}
            >
              <div className={`flex items-start gap-3 max-w-[70%] ${
                msg.role === 'user' ? 'flex-row-reverse' : ''
              }`}>
                {/* 头像 */}
                <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
                  msg.role === 'user' ? 'bg-blue-600 text-white' :
                  msg.role === 'assistant' ? 'bg-green-600 text-white' :
                  'bg-yellow-500 text-white'
                }`}>
                  {msg.role === 'user' ? (
                    <User className="w-5 h-5" />
                  ) : msg.role === 'assistant' ? (
                    <Bot className="w-5 h-5" />
                  ) : (
                    <Smile className="w-5 h-5" />
                  )}
                </div>
                
                {/* 消息内容 */}
                <div className={`rounded-xl px-4 py-3 ${
                  msg.role === 'user' ? 'bg-blue-600 text-white' :
                  msg.role === 'assistant' ? 'bg-gray-100 text-gray-800' :
                  'bg-yellow-50 text-yellow-800'
                }`}>
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef}></div>
      </div>

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
              <input type="file" multiple className="hidden" />
            </label>
            <button 
              onClick={handleSendMessage}
              disabled={isLoading || !inputMessage.trim()}
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

      {/* 设置面板 */}
      {showSettings && (
        <div className="absolute top-0 right-0 w-80 bg-white border-l border-gray-200 shadow-lg z-20 h-full">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
            <h3 className="font-semibold text-gray-800 flex items-center gap-2">
              <Settings className="w-5 h-5" /> 聊天设置
            </h3>
            <button onClick={() => setShowSettings(false)} className="text-gray-400 hover:text-gray-600">
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="p-4 space-y-6">
            {/* 上下文长度 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">上下文长度</label>
              <input
                type="range"
                min="1"
                max="20"
                defaultValue="10"
                className="w-full"
              />
              <p className="text-xs text-gray-500 mt-1">保留最近 10 条消息作为上下文</p>
            </div>
            
            {/* 温度设置 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">温度 (Temperature)</label>
              <input
                type="range"
                min="0"
                max="1"
                step="0.1"
                defaultValue="0.7"
                className="w-full"
              />
              <p className="text-xs text-gray-500 mt-1">0 = 精确, 1 = 创意</p>
            </div>
            
            {/* 最大Tokens */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">最大输出Tokens</label>
              <select className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm">
                <option value="512">512</option>
                <option value="1024">1024</option>
                <option value="2048" selected>2048</option>
                <option value="4096">4096</option>
              </select>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AIChatPanel;
import { useState, useEffect } from 'react';
import { BarChart3, Trash2, RefreshCw, Clock, Database, Search, TrendingUp, MessageSquare } from 'lucide-react';

function StatisticsPanel() {
  const [modelCalls, setModelCalls] = useState([]);
  const [searchLogs, setSearchLogs] = useState([]);
  const [activeTab, setActiveTab] = useState('model-calls');
  const [autoRefresh, setAutoRefresh] = useState(true);

  useEffect(() => {
    loadModelCalls();
    loadSearchLogs();
    
    if (autoRefresh) {
      const interval = setInterval(() => {
        if (activeTab === 'model-calls') loadModelCalls();
        else if (activeTab === 'search-logs') loadSearchLogs();
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [activeTab, autoRefresh]);

  const loadModelCalls = async () => {
    try {
      const response = await fetch('/api/model_calls?limit=50');
      const result = await response.json();
      if (result.logs) {
        setModelCalls(result.logs);
      }
    } catch (error) {
      console.error('加载模型调用日志失败:', error);
    }
  };

  const loadSearchLogs = async () => {
    try {
      const response = await fetch('/api/status');
      const result = await response.json();
      if (result.state?.search_logs) {
        setSearchLogs(result.state.search_logs);
      }
    } catch (error) {
      console.error('加载搜索日志失败:', error);
    }
  };

  const clearModelCalls = async () => {
    if (!confirm('确定要清空所有模型调用日志吗？')) return;
    try {
      const response = await fetch('/api/model_calls', { method: 'DELETE' });
      const result = await response.json();
      if (result.status === 'success') {
        loadModelCalls();
      }
    } catch (error) {
      alert('清空失败: ' + error.message);
    }
  };

  const formatMessages = (messages) => {
    if (!messages || !Array.isArray(messages)) return '';
    return messages.map(msg => {
      const roleLabels = {
        system: '系统',
        user: '用户',
        assistant: '助手'
      };
      const label = roleLabels[msg.role] || msg.role;
      return `[${label}] ${msg.content}`;
    }).join('\n\n');
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 工具栏 */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200">
        <div className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-teal-600" />
          <span className="font-semibold text-gray-800">统计分析</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setAutoRefresh(!autoRefresh);
            }}
            className={`flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg transition-colors ${
              autoRefresh 
                ? 'bg-green-100 text-green-700' 
                : 'bg-yellow-100 text-yellow-700'
            }`}
          >
            <RefreshCw className={`w-4 h-4 ${autoRefresh ? 'animate-spin' : ''}`} />
            {autoRefresh ? '实时刷新' : '已暂停'}
          </button>
        </div>
      </div>

      {/* 统计概览 */}
      <div className="grid grid-cols-4 gap-4 p-4 border-b border-gray-200">
        <div className="bg-gradient-to-br from-blue-500 to-blue-600 rounded-xl p-4 text-white">
          <div className="flex items-center gap-2 mb-2">
            <MessageSquare className="w-5 h-5" />
            <span className="text-sm opacity-90">模型调用</span>
          </div>
          <div className="text-2xl font-bold">{modelCalls.length}</div>
          <div className="text-xs opacity-70 mt-1">今日调用次数</div>
        </div>
        <div className="bg-gradient-to-br from-green-500 to-green-600 rounded-xl p-4 text-white">
          <div className="flex items-center gap-2 mb-2">
            <Search className="w-5 h-5" />
            <span className="text-sm opacity-90">搜索次数</span>
          </div>
          <div className="text-2xl font-bold">{searchLogs.length}</div>
          <div className="text-xs opacity-70 mt-1">今日搜索次数</div>
        </div>
        <div className="bg-gradient-to-br from-purple-500 to-purple-600 rounded-xl p-4 text-white">
          <div className="flex items-center gap-2 mb-2">
            <Database className="w-5 h-5" />
            <span className="text-sm opacity-90">总Token</span>
          </div>
          <div className="text-2xl font-bold">
            {modelCalls.reduce((sum, call) => sum + (call.total_tokens || 0), 0).toLocaleString()}
          </div>
          <div className="text-xs opacity-70 mt-1">已消耗Token</div>
        </div>
        <div className="bg-gradient-to-br from-orange-500 to-orange-600 rounded-xl p-4 text-white">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-5 h-5" />
            <span className="text-sm opacity-90">平均耗时</span>
          </div>
          <div className="text-2xl font-bold">
            {modelCalls.length > 0 
              ? (modelCalls.reduce((sum, call) => sum + (call.duration || 0), 0) / modelCalls.length).toFixed(1) 
              : '0'}s
          </div>
          <div className="text-xs opacity-70 mt-1">模型响应时间</div>
        </div>
      </div>

      {/* 标签页 */}
      <div className="flex border-b border-gray-200">
        <button
          onClick={() => { setActiveTab('model-calls'); loadModelCalls(); }}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'model-calls'
              ? 'border-b-2 border-blue-600 text-blue-600 bg-blue-50'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
          }`}
        >
          <MessageSquare className="w-4 h-4" /> 模型调用日志
        </button>
        <button
          onClick={() => { setActiveTab('search-logs'); loadSearchLogs(); }}
          className={`flex items-center gap-2 px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'search-logs'
              ? 'border-b-2 border-blue-600 text-blue-600 bg-blue-50'
              : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
          }`}
        >
          <Search className="w-4 h-4" /> 搜索日志
        </button>
      </div>

      {/* 内容区域 */}
      <div className="flex-1 p-4 overflow-auto">
        {activeTab === 'model-calls' ? (
          <div>
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm text-gray-600">共 {modelCalls.length} 条记录</span>
              <button
                onClick={clearModelCalls}
                className="flex items-center gap-1 px-3 py-1.5 text-sm text-red-600 border border-red-200 rounded-lg hover:bg-red-50"
              >
                <Trash2 className="w-4 h-4" /> 清空日志
              </button>
            </div>
            {modelCalls.length === 0 ? (
              <div className="text-center text-gray-400 py-12">
                <MessageSquare className="w-12 h-12 mx-auto mb-3" />
                <p>暂无模型调用记录</p>
              </div>
            ) : (
              <div className="space-y-4">
                {modelCalls.slice().reverse().map((log, index) => (
                  <div key={index} className="border border-gray-200 rounded-lg overflow-hidden">
                    <div className="bg-gradient-to-r from-blue-600 to-purple-600 text-white px-4 py-2 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span className="font-medium">📡 调用 #{modelCalls.length - index}</span>
                        <span className="text-sm opacity-90">{log.model_name}</span>
                      </div>
                      <span className="text-sm opacity-90">
                        {new Date(log.timestamp).toLocaleString('zh-CN')}
                      </span>
                    </div>
                    <div className="p-4">
                      {log.error ? (
                        <div className="bg-red-50 border-l-4 border-red-500 p-3 mb-3">
                          <span className="text-red-700 font-medium">❌ 调用失败</span>
                          <p className="text-red-600 text-sm mt-1">{log.error}</p>
                        </div>
                      ) : (
                        <>
                          <div className="mb-3">
                            <div className="text-blue-600 font-medium text-sm mb-2">📤 输入 ({log.prompt_tokens} tokens)</div>
                            <div className="bg-gray-50 p-3 rounded-lg text-sm font-mono max-h-40 overflow-auto whitespace-pre-wrap">
                              {formatMessages(log.messages)}
                            </div>
                          </div>
                          <div>
                            <div className="text-green-600 font-medium text-sm mb-2">📥 输出 ({log.completion_tokens} tokens)</div>
                            <div className="bg-green-50 p-3 rounded-lg text-sm font-mono max-h-60 overflow-auto whitespace-pre-wrap">
                              {log.response || '(空响应)'}
                            </div>
                          </div>
                        </>
                      )}
                      <div className="flex gap-4 mt-3 pt-3 border-t border-gray-100 text-xs text-gray-500">
                        <span>⏱️ 耗时: {(log.duration || 0).toFixed(2)}s</span>
                        <span>📊 总tokens: {log.total_tokens}</span>
                        <span>📝 输入: {log.prompt_tokens}</span>
                        <span>📤 输出: {log.completion_tokens}</span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div>
            {searchLogs.length === 0 ? (
              <div className="text-center text-gray-400 py-12">
                <Search className="w-12 h-12 mx-auto mb-3" />
                <p>暂无搜索记录</p>
              </div>
            ) : (
              <div className="space-y-4">
                {searchLogs.slice().reverse().map((log, index) => (
                  <div key={index} className="border border-gray-200 rounded-lg p-4">
                    <div className="flex items-center justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <span className="font-medium">搜索 #{searchLogs.length - index}</span>
                        <span className="text-sm text-gray-500">迭代 {log.iteration}</span>
                      </div>
                      <span className="text-xs text-gray-400">{log.timestamp}</span>
                    </div>
                    <div className="flex items-center gap-2 mb-3">
                      <Search className="w-4 h-4 text-blue-500" />
                      <span className="font-medium">{log.query}</span>
                      <span className="text-xs text-gray-500 ml-auto">
                        {log.result_count} 条结果 | {log.elapsed_time}s
                      </span>
                    </div>
                    {log.error ? (
                      <div className="text-red-600 text-sm">
                        <i className="fas fa-exclamation-circle"></i> {log.error}
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {log.results && log.results.slice(0, 3).map((result, idx) => (
                          <div key={idx} className="text-sm">
                            <div className="flex items-center gap-2">
                              <span className="text-blue-600 font-medium">{idx + 1}.</span>
                              <a href={result.url} target="_blank" className="text-blue-600 hover:underline">
                                {result.title}
                              </a>
                            </div>
                            {result.snippet && <p className="text-gray-500 text-xs ml-6">{result.snippet}</p>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default StatisticsPanel;
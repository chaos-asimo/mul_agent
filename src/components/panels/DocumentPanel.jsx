import { useState, useEffect, useRef, useCallback } from 'react';
import { Upload, Trash2, Users, Play, Square, Terminal, Code, Eye, Maximize2, Minimize2, Clock, RotateCcw, Coins, Search, FileText, Download, X, Check } from 'lucide-react';
import { marked } from 'marked';

function DocumentPanel() {
  const [inputContent, setInputContent] = useState('生成一个公积金数据运营的完整方案，可实操，可持续盈利，并能打动投资人。');
  const [previewContent, setPreviewContent] = useState('');
  const [logs, setLogs] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [iterations, setIterations] = useState(1);
  const [viewMode, setViewMode] = useState('preview');
  const [status, setStatus] = useState('idle');
  const [statusDotClass, setStatusDotClass] = useState('bg-green-500');
  
  const [stats, setStats] = useState({
    tokens: 0,
    searches: 0,
    time: '00:00:00',
    wordcount: 0,
    progress: 0,
    iteration: 0,
    total_iterations: 1,
    current_step: 0,
    total_steps: 0
  });

  const [agents, setAgents] = useState([]);
  const [selectedAgents, setSelectedAgents] = useState([]);
  const [showAgentDialog, setShowAgentDialog] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [maximizedPanel, setMaximizedPanel] = useState(null);

  const logsEndRef = useRef(null);
  const statusIntervalRef = useRef(null);
  const wsRef = useRef(null);
  const previewRef = useRef(null);

  const toggleMaximize = (panelName) => {
    setMaximizedPanel(prev => prev === panelName ? null : panelName);
  };

  useEffect(() => {
    if (previewRef.current && isProcessing) {
      previewRef.current.scrollTop = previewRef.current.scrollHeight;
    }
  }, [previewContent, isProcessing]);

  useEffect(() => {
    loadAgents();
    loadAttachments();
    startStatusPolling();
    return () => {
      stopStatusPolling();
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  useEffect(() => {
    setStats(prev => ({ ...prev, wordcount: inputContent.length }));
  }, [inputContent]);

  const loadAgents = async () => {
    try {
      const response = await fetch('/api/agents');
      const result = await response.json();
      if (result.groups) {
        const allAgents = [];
        result.groups.forEach(group => {
          if (group.agents) {
            allAgents.push(...group.agents);
          }
        });
        setAgents(allAgents);
      }
    } catch (error) {
      console.error('加载Agents失败:', error);
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
          addLog(`附件上传成功: ${result.filename}`);
        } else {
          addLog(`附件上传失败: ${result.message}`);
        }
      } catch (error) {
        addLog(`上传失败: ${error.message}`);
      }
    }
    await loadAttachments();
    e.target.value = '';
  };

  const clearAttachments = async () => {
    if (!confirm('确定要清空所有附件吗？')) return;
    try {
      const response = await fetch('/api/attachments/clear', { method: 'POST' });
      const result = await response.json();
      if (result.status === 'success') {
        addLog(result.message);
        await loadAttachments();
      }
    } catch (error) {
      addLog(`清空失败: ${error.message}`);
    }
  };

  const addLog = (message, scroll = true) => {
    setLogs(prev => [...prev, message]);
  };

  const clearLogs = () => {
    setLogs([]);
    addLog('日志已清空');
  };

  const exportLogs = async () => {
    try {
      const response = await fetch('/api/logs/export', { method: 'POST' });
      if (!response.ok) {
        const result = await response.json();
        alert(result.message || '导出失败');
        return;
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'logs_export.txt';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      addLog('日志已导出');
    } catch (error) {
      alert(`导出失败: ${error.message}`);
    }
  };

  const openAgentDialog = () => {
    setShowAgentDialog(true);
  };

  const toggleAgentSelection = (agentId) => {
    setSelectedAgents(prev => {
      if (prev.includes(agentId)) {
        return prev.filter(id => id !== agentId);
      } else {
        return [...prev, agentId];
      }
    });
  };

  const selectAllAgents = () => {
    setSelectedAgents(agents.map(a => a.id));
  };

  const deselectAllAgents = () => {
    setSelectedAgents([]);
  };

  const startStatusPolling = () => {
    stopStatusPolling();
    const poll = async () => {
      try {
        const response = await fetch('/api/status');
        const statusData = await response.json();
        
        setStatus(statusData.status || 'idle');
        
        // 更新状态点颜色
        if (statusData.status === 'processing') {
          setStatusDotClass('bg-yellow-500 animate-pulse');
        } else if (statusData.status === 'completed') {
          setStatusDotClass('bg-green-500');
        } else if (statusData.status === 'error' || statusData.status === 'stopped') {
          setStatusDotClass('bg-red-500');
        } else {
          setStatusDotClass('bg-green-500');
        }

        // 更新文档内容
        if (statusData.status === 'processing' && statusData.current_document) {
          setInputContent(statusData.current_document);
          updatePreview(statusData.current_document);
        }

        // 更新统计信息
        if (statusData.state) {
          const totalIterations = statusData.state.total_iterations || iterations;
          setStats(prev => ({
            ...prev,
            iteration: statusData.state.current_iteration || 0,
            total_iterations: totalIterations,
            tokens: statusData.state.total_tokens || 0,
            searches: statusData.state.search_count || 0,
            current_step: statusData.state.current_step || 0,
            total_steps: statusData.state.total_steps || 0
          }));

          // 更新运行时长
          if (statusData.state.elapsed_time) {
            const seconds = Math.floor(statusData.state.elapsed_time);
            const hh = String(Math.floor(seconds / 3600)).padStart(2, '0');
            const mm = String(Math.floor((seconds % 3600) / 60)).padStart(2, '0');
            const ss = String(seconds % 60).padStart(2, '0');
            setStats(prev => ({ ...prev, time: `${hh}:${mm}:${ss}` }));
          }

          // 更新进度条
          if (statusData.state.progress_percent !== undefined) {
            setStats(prev => ({ ...prev, progress: statusData.state.progress_percent }));
          } else if (totalIterations > 0 && statusData.state.current_iteration) {
            const progress = Math.round((statusData.state.current_iteration / totalIterations) * 100);
            setStats(prev => ({ ...prev, progress }));
          }
        }

        // 更新日志
        if (statusData.log && statusData.log.length > 0) {
          const existingLogs = new Set(logs);
          statusData.log.forEach(entry => {
            if (!existingLogs.has(entry)) {
              addLog(entry);
            }
          });
        }

        // 更新Agent状态
        if (statusData.agent_results) {
          setAgents(prev => prev.map(agent => {
            const result = statusData.agent_results[agent.id];
            if (result) {
              return {
                ...agent,
                status: result.success ? 'completed' : 'error',
                stats: {
                  model_name: result.model_name,
                  iteration: result.iteration,
                  prompt_tokens: result.prompt_tokens,
                  completion_tokens: result.completion_tokens,
                  time_spent: result.time_spent
                }
              };
            }
            return agent;
          }));
        }

      } catch (error) {
        console.error('获取状态失败:', error);
      }
    };
    statusIntervalRef.current = setInterval(poll, 3000);
  };

  const stopStatusPolling = () => {
    if (statusIntervalRef.current) {
      clearInterval(statusIntervalRef.current);
      statusIntervalRef.current = null;
    }
  };

  const handleStartProcessing = async () => {
    const content = inputContent.trim();
    if (!content) {
      alert('请先输入内容');
      return;
    }

    // 分析是否需要调用Skill
    try {
      const analyzeResponse = await fetch('/api/skills/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content })
      });
      const analyzeResult = await analyzeResponse.json();

      if (analyzeResult.matched_skills && analyzeResult.matched_skills.length > 0) {
        const selectedSkills = await showSkillSelectionDialog(analyzeResult.matched_skills);
        if (selectedSkills === null) return;
        
        if (selectedSkills.length > 0) {
          addLog(`准备执行 ${selectedSkills.length} 个Skill...`);
          for (const skillId of selectedSkills) {
            addLog(`执行Skill: ${skillId}...`);
            try {
              const execResponse = await fetch(`/api/skills/${skillId}/execute`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ params: { query: content } })
              });
              const execResult = await execResponse.json();
              if (execResult.result?.success) {
                addLog(`Skill执行成功`);
              } else {
                addLog(`Skill执行失败: ${execResult.message}`);
              }
            } catch (err) {
              addLog(`Skill执行异常: ${err.message}`);
            }
          }
        }
      }
    } catch (error) {
      console.error('Skill分析失败:', error);
    }

    setIsProcessing(true);
    setStatus('processing');
    setStatusDotClass('bg-yellow-500 animate-pulse');
    setLogs(['开始处理任务...']);
    setStats(prev => ({ ...prev, progress: 0, iteration: 0, current_step: 0 }));

    // 停止状态轮询，使用WebSocket
    stopStatusPolling();

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/process`;
    
    wsRef.current = new WebSocket(wsUrl);
    
    let accumulatedContent = content;

    wsRef.current.onopen = () => {
      addLog('WebSocket已连接，开始处理...');
      wsRef.current.send(JSON.stringify({
        content,
        iterations: parseInt(iterations),
        enable_search: true,
        agent_ids: selectedAgents
      }));
    };

    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        if (data.status === 'log') {
          addLog(data.message);
        } else if (data.status === 'error') {
          addLog(`✗ ${data.message}`);
          setIsProcessing(false);
          setStatus('error');
          setStatusDotClass('bg-red-500');
        } else if (data.status === 'started') {
          addLog(`▶ ${data.message}`);
        } else if (data.status === 'stats') {
          setStats(prev => ({
            ...prev,
            iteration: data.iteration || 0,
            total_iterations: data.total_iterations || prev.total_iterations,
            current_step: data.current_step || 0,
            total_steps: data.total_steps || prev.total_steps,
            tokens: data.total_tokens || 0,
            searches: data.searches || 0,
            time: data.elapsed_time || prev.time,
            progress: data.total_steps > 0 ? Math.round(((data.current_step || 0) / data.total_steps) * 100) : prev.progress
          }));
        } else if (data.status === 'chunk' && data.content) {
          accumulatedContent += data.content;
          setInputContent(accumulatedContent);
          updatePreview(accumulatedContent);
        } else if (data.status === 'agent_start') {
          addLog(`⚡ ${data.agent} (${data.model})`);
        } else if (data.status === 'agent_complete') {
          addLog(`✓ ${data.agent} 完成`);
        } else if (data.status === 'completed' && data.content) {
          accumulatedContent = data.content;
          setInputContent(accumulatedContent);
          updatePreview(accumulatedContent);
          addLog('✓ 处理完成');
          setIsProcessing(false);
          setStatus('completed');
          setStatusDotClass('bg-green-500');
          setStats(prev => ({ ...prev, progress: 100 }));
          
          if (wsRef.current) {
            wsRef.current.close();
          }
          startStatusPolling();
        }
      } catch (e) {
        console.error('解析WebSocket数据失败:', e);
      }
    };

    wsRef.current.onerror = (error) => {
      addLog(`✗ WebSocket错误: ${error.message || '未知错误'}`);
      setIsProcessing(false);
      setStatus('error');
      setStatusDotClass('bg-red-500');
      startStatusPolling();
    };

    wsRef.current.onclose = () => {
      if (isProcessing) {
        addLog('WebSocket连接已关闭');
      }
      startStatusPolling();
    };
  };

  const showSkillSelectionDialog = (matchedSkills) => {
    return new Promise((resolve) => {
      // 简化实现：默认跳过Skill选择
      resolve([]);
    });
  };

  const handleStopProcessing = async () => {
    try {
      const response = await fetch('/api/stop', { method: 'POST' });
      const result = await response.json();
      if (result.status === 'success') {
        addLog(result.message);
      }
    } catch (error) {
      addLog(`停止失败: ${error.message}`);
    }
    setIsProcessing(false);
    setStatus('stopped');
    setStatusDotClass('bg-red-500');
    if (wsRef.current) {
      wsRef.current.close();
    }
  };

  const handleClearAll = async () => {
    if (!confirm('确定要清空所有内容吗？')) return;
    try {
      const response = await fetch('/api/clear', { method: 'POST' });
      const result = await response.json();
      if (result.status === 'success') {
        addLog(result.message);
        setInputContent('');
        setPreviewContent('');
        setLogs([]);
        setStats({
          tokens: 0,
          searches: 0,
          time: '00:00:00',
          wordcount: 0,
          progress: 0,
          iteration: 0,
          total_iterations: iterations,
          current_step: 0,
          total_steps: 0
        });
        await loadAttachments();
      }
    } catch (error) {
      addLog(`清空失败: ${error.message}`);
    }
  };

  const updatePreview = (content) => {
    if (viewMode === 'markdown') {
      setPreviewContent(content);
    } else {
      setPreviewContent(marked.parse(content) || '');
    }
  };

  const handleSaveDocument = async () => {
    const content = inputContent.trim();
    if (!content) {
      alert('没有可保存的内容');
      return;
    }
    const filename = prompt('请输入文件名:', 'document');
    if (!filename) return;
    
    try {
      const formData = new FormData();
      formData.append('content', content);
      formData.append('filename', filename);
      const response = await fetch('/api/save', {
        method: 'POST',
        body: formData
      });
      const result = await response.json();
      if (result.status === 'success') {
        addLog(result.message);
      } else {
        alert(result.message);
      }
    } catch (error) {
      alert(`保存失败: ${error.message}`);
    }
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 工具栏 */}
      <div className={`flex items-center justify-between px-4 py-3 bg-gray-50 border-b border-gray-200 ${maximizedPanel ? 'hidden' : ''}`}>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg cursor-pointer hover:bg-blue-700">
            <Upload className="w-4 h-4" /> 上传
            <input type="file" multiple accept=".doc,.docx,.pdf,.txt" className="hidden" onChange={handleFileUpload} />
          </label>
          <button onClick={clearAttachments} className="flex items-center gap-2 px-3 py-2 text-red-600 border border-red-200 rounded-lg hover:bg-red-50">
            <Trash2 className="w-4 h-4" /> 清空附件
          </button>
          <button onClick={openAgentDialog} className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
            <Users className="w-4 h-4" /> 角色选择 ({selectedAgents.length})
          </button>
          <button 
            onClick={handleStartProcessing}
            disabled={isProcessing}
            className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
          >
            <Play className="w-4 h-4" /> 开始处理
          </button>
          <button 
            onClick={handleStopProcessing}
            disabled={!isProcessing}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
          >
            <Square className="w-4 h-4" /> 停止处理
          </button>
          <button 
            onClick={handleClearAll}
            className="flex items-center gap-2 px-3 py-2 text-red-600 border border-red-200 rounded-lg hover:bg-red-50"
          >
            <Trash2 className="w-4 h-4" /> 清空
          </button>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-600">迭代次数:</span>
            <input 
              type="number" 
              value={iterations}
              onChange={(e) => {
                setIterations(e.target.value);
                setStats(prev => ({ ...prev, total_iterations: parseInt(e.target.value) || 1 }));
              }}
              min="1" max="50"
              className="w-20 px-2 py-1 border border-gray-200 rounded text-sm"
            />
          </div>
          <div className="flex items-center gap-2">
            <span className={`w-3 h-3 rounded-full ${statusDotClass}`}></span>
            <span className="text-sm text-gray-600">
              {status === 'processing' ? '处理中' : status === 'completed' ? '已完成' : status === 'error' ? '错误' : status === 'stopped' ? '已停止' : '就绪'}
            </span>
          </div>
        </div>
      </div>

      {/* 附件列表 */}
      {!maximizedPanel && attachments.length > 0 && (
        <div className="px-4 py-2 bg-blue-50 border-b border-blue-100">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-blue-600 font-medium">已上传附件:</span>
            {attachments.map((file, index) => (
              <span key={index} className="inline-flex items-center gap-1 px-2 py-1 bg-blue-100 text-blue-600 rounded-full text-xs">
                <FileText className="w-3 h-3" />
                {file.length > 20 ? file.substring(0, 20) + '...' : file}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* 统计信息栏 */}
      <div className={`flex items-center gap-6 px-4 py-3 bg-gray-50 border-b border-gray-200 ${maximizedPanel ? 'hidden' : ''}`}>
        <div className="flex items-center gap-2">
          <RotateCcw className="w-5 h-5 text-gray-500" />
          <div>
            <span className="text-xs text-gray-500">迭代进度</span>
            <div className="text-sm font-medium">
              {stats.iteration}/{stats.total_iterations}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Coins className="w-5 h-5 text-yellow-500" />
          <div>
            <span className="text-xs text-gray-500">总Token</span>
            <div className="text-sm font-medium">{stats.tokens.toLocaleString()}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Search className="w-5 h-5 text-blue-500" />
          <div>
            <span className="text-xs text-gray-500">搜索次数</span>
            <div className="text-sm font-medium">{stats.searches}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Clock className="w-5 h-5 text-gray-500" />
          <div>
            <span className="text-xs text-gray-500">运行时长</span>
            <div className="text-sm font-medium">{stats.time}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <FileText className="w-5 h-5 text-blue-500" />
          <div>
            <span className="text-xs text-gray-500">字数统计</span>
            <div className="text-sm font-medium">{stats.wordcount}</div>
          </div>
        </div>
        <div className="flex-1 flex items-center gap-2">
          <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div 
              className="h-full bg-blue-600 transition-all" 
              style={{ width: `${stats.progress}%` }}
            ></div>
          </div>
          <span className="text-sm text-gray-600">{stats.progress}%</span>
        </div>
        <div className="text-sm text-gray-500">
          步骤 {stats.current_step}/{stats.total_steps}
        </div>
      </div>

      {/* 工作区域 */}
      <div className={`flex-1 flex gap-4 p-4 min-h-0 overflow-hidden ${maximizedPanel && maximizedPanel !== 'preview' ? 'hidden' : ''}`}>
        {/* 左半部分：输入指令 */}
        <div className={`flex-1 flex flex-col min-w-0 min-h-0 ${maximizedPanel === 'preview' ? 'hidden' : ''}`}>
          <div className="flex items-center gap-2 mb-2">
            <Terminal className="w-5 h-5 text-gray-600" />
            <span className="font-medium text-gray-800">输入指令</span>
          </div>
          <textarea
            value={inputContent}
            onChange={(e) => setInputContent(e.target.value)}
            placeholder="请输入您的指令或需求..."
            className="flex-1 px-4 py-3 border border-gray-200 rounded-lg resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none text-sm font-mono overflow-auto"
          />
        </div>

        {/* 右半部分：预览区域 */}
        <div className={`flex-1 flex flex-col min-w-0 min-h-0 ${maximizedPanel === 'preview' ? 'flex-[100]' : ''}`}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-gray-500" />
              <span className="font-medium text-gray-800">文档预览</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="flex border border-gray-200 rounded-lg">
                <button 
                  onClick={() => setViewMode('markdown')}
                  className={`flex items-center gap-1 px-3 py-1.5 text-sm rounded-l-lg transition-colors ${
                    viewMode === 'markdown' ? 'bg-gray-100 text-gray-800' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Code className="w-4 h-4" /> 源码
                </button>
                <button 
                  onClick={() => setViewMode('preview')}
                  className={`flex items-center gap-1 px-3 py-1.5 text-sm rounded-r-lg transition-colors ${
                    viewMode === 'preview' ? 'bg-gray-100 text-gray-800' : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Eye className="w-4 h-4" /> 预览
                </button>
              </div>
              <button 
                onClick={() => toggleMaximize('preview')} 
                className="p-1.5 text-gray-400 hover:text-gray-600" 
                title={maximizedPanel === 'preview' ? '恢复' : '最大化'}
              >
                {maximizedPanel === 'preview' ? (
                  <Minimize2 className="w-4 h-4" />
                ) : (
                  <Maximize2 className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
          <div ref={previewRef} className="flex-1 p-4 bg-gray-50 border border-gray-200 rounded-lg overflow-auto">
            {previewContent ? (
              viewMode === 'markdown' ? (
                <pre className="whitespace-pre-wrap text-sm font-mono">{previewContent}</pre>
              ) : (
                <div className="prose prose-sm" dangerouslySetInnerHTML={{ __html: previewContent }}></div>
              )
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-400">
                <FileText className="w-12 h-12 mb-3" />
                <p>处理后的文档将在这里显示</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 底部面板 */}
      <div className={`flex gap-4 px-4 pb-4 pt-2 border-t border-gray-200 min-h-0 ${maximizedPanel && maximizedPanel !== 'agents' && maximizedPanel !== 'logs' ? 'hidden' : ''} ${maximizedPanel === 'agents' || maximizedPanel === 'logs' ? 'flex-1' : 'max-h-48'}`}>
        {/* Agent状态 */}
        <div className={`flex-1 flex flex-col min-h-0 ${maximizedPanel === 'logs' ? 'hidden' : ''}`}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Terminal className="w-5 h-5 text-gray-600" />
              <span className="font-medium text-gray-800">Agent状态</span>
            </div>
            <button 
              onClick={() => toggleMaximize('agents')} 
              className="p-1.5 text-gray-400 hover:text-gray-600" 
              title={maximizedPanel === 'agents' ? '恢复' : '最大化'}
            >
              {maximizedPanel === 'agents' ? (
                <Minimize2 className="w-4 h-4" />
              ) : (
                <Maximize2 className="w-4 h-4" />
              )}
            </button>
          </div>
          <div className="flex-1 bg-gray-50 rounded-lg overflow-hidden min-h-0">
            <div className="overflow-auto h-full">
              <table className="w-full text-sm">
                <thead className="bg-gray-100 sticky top-0">
                  <tr>
                    <th className="px-3 py-2 text-left font-medium">Agent</th>
                    <th className="px-3 py-2 text-left font-medium">状态</th>
                    <th className="px-3 py-2 text-left font-medium">模型</th>
                    <th className="px-3 py-2 text-left font-medium">迭代</th>
                    <th className="px-3 py-2 text-left font-medium">输入Token</th>
                    <th className="px-3 py-2 text-left font-medium">输出Token</th>
                    <th className="px-3 py-2 text-left font-medium">耗时</th>
                  </tr>
                </thead>
                <tbody>
                  {agents.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-3 py-4 text-center text-gray-400">暂无Agent</td>
                    </tr>
                  ) : (
                    agents.map((agent) => (
                      <tr key={agent.id} className="border-t border-gray-200">
                        <td className="px-3 py-2">{agent.name}</td>
                        <td className="px-3 py-2">
                          <span className={`px-2 py-0.5 rounded text-xs ${
                            agent.status === 'completed' ? 'bg-green-100 text-green-600' :
                            agent.status === 'error' ? 'bg-red-100 text-red-600' :
                            agent.status === 'running' ? 'bg-yellow-100 text-yellow-600' :
                            'bg-gray-100 text-gray-500'
                          }`}>
                            {agent.status === 'completed' ? '完成' :
                             agent.status === 'error' ? '失败' :
                             agent.status === 'running' ? '运行中' : '就绪'}
                          </span>
                        </td>
                        <td className="px-3 py-2">{agent.stats?.model_name || '-'}</td>
                        <td className="px-3 py-2">{agent.stats?.iteration || '0'}</td>
                        <td className="px-3 py-2">{agent.stats?.prompt_tokens || '0'}</td>
                        <td className="px-3 py-2">{agent.stats?.completion_tokens || '0'}</td>
                        <td className="px-3 py-2">{agent.stats?.time_spent ? `${agent.stats.time_spent.toFixed(1)}s` : '0s'}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* 日志区域 */}
        <div className={`flex-1 flex flex-col min-h-0 ${maximizedPanel === 'agents' ? 'hidden' : ''}`}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Terminal className="w-5 h-5 text-gray-600" />
              <span className="font-medium text-gray-800">处理日志</span>
            </div>
            <div className="flex items-center gap-2">
              <select className="px-2 py-1 border border-gray-200 rounded text-sm">
                <option value="ALL">全部</option>
                <option value="DEBUG">DEBUG</option>
                <option value="INFO" selected>INFO</option>
                <option value="WARNING">WARNING</option>
                <option value="ERROR">ERROR</option>
              </select>
              <button onClick={clearLogs} className="p-1.5 text-gray-400 hover:text-gray-600" title="清空日志">
                <Trash2 className="w-4 h-4" />
              </button>
              <button onClick={exportLogs} className="p-1.5 text-gray-400 hover:text-gray-600" title="导出日志">
                <Download className="w-4 h-4" />
              </button>
              <button 
                onClick={() => toggleMaximize('logs')} 
                className="p-1.5 text-gray-400 hover:text-gray-600" 
                title={maximizedPanel === 'logs' ? '恢复' : '最大化'}
              >
                {maximizedPanel === 'logs' ? (
                  <Minimize2 className="w-4 h-4" />
                ) : (
                  <Maximize2 className="w-4 h-4" />
                )}
              </button>
            </div>
          </div>
          <div className="flex-1 bg-gray-900 text-gray-300 rounded-lg p-3 overflow-auto text-sm font-mono" ref={logsEndRef}>
            {logs.length > 0 ? (
              logs.map((log, index) => (
                <div key={index} className={`mb-1 ${
                  log.includes('✓') || log.includes('成功') ? 'text-green-400' :
                  log.includes('✗') || log.includes('失败') || log.includes('错误') ? 'text-red-400' :
                  log.includes('⚠') || log.includes('警告') ? 'text-yellow-400' :
                  ''
                }`}>
                  {log}
                </div>
              ))
            ) : (
              <div className="text-gray-500">日志将在这里显示...</div>
            )}
          </div>
        </div>
      </div>

      {/* 角色选择对话框 */}
      {showAgentDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl w-full max-w-2xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <Users className="w-5 h-5" /> 选择Agent
              </h3>
              <button onClick={() => setShowAgentDialog(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-4">
              <div className="flex items-center justify-between mb-4">
                <span className="text-sm text-gray-600">已选择 {selectedAgents.length} 个Agent</span>
                <div className="flex gap-2">
                  <button onClick={selectAllAgents} className="text-sm text-blue-600 hover:underline">全选</button>
                  <button onClick={deselectAllAgents} className="text-sm text-blue-600 hover:underline">取消全选</button>
                </div>
              </div>
              <div className="space-y-2 max-h-80 overflow-auto">
                {agents.map((agent) => (
                  <div
                    key={agent.id}
                    onClick={() => toggleAgentSelection(agent.id)}
                    className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                      selectedAgents.includes(agent.id)
                        ? 'bg-blue-50 border border-blue-200'
                        : 'bg-gray-50 border border-gray-100 hover:bg-gray-100'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={selectedAgents.includes(agent.id)}
                      onChange={() => {}}
                      className="w-4 h-4 text-blue-600 rounded"
                    />
                    <div className="flex-1">
                      <div className="font-medium text-gray-800">{agent.name}</div>
                      <div className="text-sm text-gray-500">{agent.role_description || '无描述'}</div>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-xs ${
                      agent.enabled ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-500'
                    }`}>
                      {agent.enabled ? '已启用' : '已禁用'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200">
              <button onClick={() => setShowAgentDialog(false)} className="px-4 py-2 text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50">
                取消
              </button>
              <button onClick={() => setShowAgentDialog(false)} className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
                确定 ({selectedAgents.length})
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default DocumentPanel;
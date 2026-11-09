import { useState, useEffect } from 'react';
import { Coins, Sparkles, BookOpen, ChevronRight, RefreshCw, Wand2, Info } from 'lucide-react';

const YAO_PAIRS = {
  '6': { name: '老阴', symbol: '☷', color: 'text-blue-600', bg: 'bg-blue-100', change: '变阳' },
  '7': { name: '少阳', symbol: '☰', color: 'text-green-600', bg: 'bg-green-100', change: null },
  '8': { name: '少阴', symbol: '☷', color: 'text-gray-600', bg: 'bg-gray-100', change: null },
  '9': { name: '老阳', symbol: '☰', color: 'text-red-600', bg: 'bg-red-100', change: '变阴' },
};

const GUA_INFO = {
  '1': { name: '乾', description: '天行健，君子以自强不息', attributes: '元亨利贞' },
  '2': { name: '坤', description: '地势坤，君子以厚德载物', attributes: '元亨，利牝马之贞' },
  '3': { name: '屯', description: '云雷屯，君子以经纶', attributes: '元亨利贞，勿用有攸往' },
  '4': { name: '蒙', description: '山下出泉，君子以果行育德', attributes: '亨。匪我求童蒙，童蒙求我' },
  '5': { name: '需', description: '云上于天，君子以饮食宴乐', attributes: '有孚，光亨，贞吉' },
  '6': { name: '讼', description: '天与水违行，君子以作事谋始', attributes: '有孚窒惕，中吉终凶' },
  '7': { name: '师', description: '地中有水，君子以容民畜众', attributes: '贞，丈人吉，无咎' },
  '8': { name: '比', description: '地上有水，先王以建万国，亲诸侯', attributes: '吉。原筮，元永贞，无咎' },
  '9': { name: '小畜', description: '风行天上，君子以懿文德', attributes: '亨。密云不雨，自我西郊' },
  '10': { name: '履', description: '上天下泽，君子以辩上下，定民志', attributes: '履虎尾，不咥人，亨' },
};

function YijingPanel() {
  const [currentStep, setCurrentStep] = useState(0);
  const [yaoResults, setYaoResults] = useState([]);
  const [isShaking, setIsShaking] = useState(false);
  const [mainGua, setMainGua] = useState(null);
  const [changeGua, setChangeGua] = useState(null);
  const [aiAnalysis, setAiAnalysis] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [question, setQuestion] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState([]);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      const response = await fetch('/api/yijing/history');
      const data = await response.json();
      setHistory(data.history || []);
    } catch (error) {
      console.error('加载卜卦历史失败:', error);
    }
  };

  const castYao = () => {
    if (currentStep >= 6) return;
    
    setIsShaking(true);
    setTimeout(() => {
      const random = Math.random();
      let result;
      if (random < 0.125) result = '6';    // 老阴 1/8
      else if (random < 0.25) result = '7'; // 少阳 1/8
      else if (random < 0.375) result = '8'; // 少阴 1/8
      else if (random < 0.5) result = '9';   // 老阳 1/8
      else if (random < 0.625) result = '6';  // 老阴 1/8
      else if (random < 0.75) result = '7';   // 少阳 1/8
      else if (random < 0.875) result = '8';  // 少阴 1/8
      else result = '9';                      // 老阳 1/8
      
      setYaoResults(prev => [...prev, result]);
      setCurrentStep(prev => prev + 1);
      setIsShaking(false);
    }, 1000);
  };

  const calculateGua = () => {
    if (yaoResults.length !== 6) return;
    
    // 计算本卦
    let guaCode = '';
    let changeGuaCode = '';
    
    yaoResults.forEach(yao => {
      guaCode += yao;
      if (yao === '6') {
        changeGuaCode += '9'; // 老阴变阳
      } else if (yao === '9') {
        changeGuaCode += '6'; // 老阳变阴
      } else {
        changeGuaCode += yao;
      }
    });
    
    // 根据卦码计算卦号（简化实现）
    const guaNumber = Math.floor(Math.random() * 10) + 1;
    setMainGua({ ...GUA_INFO[guaNumber], code: guaCode, number: guaNumber });
    
    if (changeGuaCode !== guaCode) {
      const changeNumber = Math.floor(Math.random() * 10) + 1;
      setChangeGua({ ...GUA_INFO[changeNumber], code: changeGuaCode, number: changeNumber });
    } else {
      setChangeGua(null);
    }
  };

  useEffect(() => {
    if (currentStep === 6) {
      calculateGua();
    }
  }, [currentStep]);

  const handleAiAnalysis = async () => {
    if (!mainGua) return;
    
    setIsAnalyzing(true);
    setAiAnalysis('');
    
    try {
      const response = await fetch('/api/yijing/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: question || '请解此卦',
          main_gua: mainGua,
          change_gua: changeGua,
          yao_results: yaoResults
        })
      });
      
      if (!response.ok) {
        throw new Error('分析失败');
      }
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let content = '';
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        content += chunk;
        setAiAnalysis(content);
      }
      
      // 保存到历史
      try {
        await fetch('/api/yijing/history', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: question || '无',
            main_gua: mainGua,
            change_gua: changeGua,
            yao_results: yaoResults,
            analysis: content
          })
        });
        await loadHistory();
      } catch (e) {
        console.error('保存历史失败:', e);
      }
      
    } catch (error) {
      setAiAnalysis(`分析失败: ${error.message}`);
    } finally {
      setIsAnalyzing(false);
    }
  };

  const reset = () => {
    setCurrentStep(0);
    setYaoResults([]);
    setMainGua(null);
    setChangeGua(null);
    setAiAnalysis('');
    setQuestion('');
  };

  const getYaoLine = (yao, index) => {
    const info = YAO_PAIRS[yao];
    const position = ['初', '二', '三', '四', '五', '上'][index];
    return (
      <div key={index} className={`flex items-center gap-4 p-3 rounded-lg ${info.bg} border border-gray-200`}>
        <div className="w-12 text-center">
          <span className="text-sm text-gray-500">{position}爻</span>
        </div>
        <div className={`text-4xl ${info.color}`}>{info.symbol}</div>
        <div className="flex-1">
          <span className={`font-medium ${info.color}`}>{info.name}</span>
          {info.change && (
            <span className="ml-2 text-xs text-orange-600">({info.change})</span>
          )}
        </div>
        <div className="text-lg font-bold text-gray-600">
          {yao === '6' ? '×' : yao === '9' ? '○' : ''}
        </div>
      </div>
    );
  };

  return (
    <div className="h-full flex flex-col bg-white">
      {/* 顶部标题 */}
      <div className="flex items-center justify-between px-4 py-4 bg-gradient-to-r from-yellow-500 to-orange-500 text-white">
        <div className="flex items-center gap-3">
          <Coins className="w-8 h-8" />
          <h2 className="text-xl font-bold">周易卜卦</h2>
        </div>
        <button 
          onClick={() => setShowHistory(!showHistory)}
          className="flex items-center gap-2 px-3 py-2 bg-white bg-opacity-20 rounded-lg hover:bg-opacity-30"
        >
          <BookOpen className="w-5 h-5" /> 历史记录
        </button>
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* 左侧：卜卦区域 */}
        <div className="flex-1 p-4 overflow-auto">
          {/* 输入问题 */}
          {currentStep === 0 && !mainGua && (
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">
                您想问什么？
              </label>
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="请输入您想问的问题，例如：近期运势如何？"
                className="w-full px-4 py-3 border border-gray-200 rounded-xl resize-none focus:ring-2 focus:ring-yellow-500 focus:border-transparent outline-none text-sm"
                rows={3}
              />
            </div>
          )}

          {/* 卦爻展示 */}
          <div className="mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium text-gray-800">六爻结果</h3>
              <span className="text-sm text-gray-500">已摇 {currentStep}/6 爻</span>
            </div>
            
            <div className="space-y-2">
              {yaoResults.map((yao, index) => getYaoLine(yao, index))}
              {currentStep < 6 && (
                <div className={`flex items-center justify-center p-8 border-2 border-dashed rounded-lg ${
                  isShaking ? 'animate-pulse border-yellow-400 bg-yellow-50' : 'border-gray-200'
                }`}>
                  {isShaking ? (
                    <div className="flex flex-col items-center">
                      <RefreshCw className="w-12 h-12 text-yellow-500 animate-spin mb-3" />
                      <span className="text-yellow-600">正在摇卦...</span>
                    </div>
                  ) : (
                    <button
                      onClick={castYao}
                      className="flex flex-col items-center gap-3 px-8 py-6 bg-yellow-500 text-white rounded-xl hover:bg-yellow-600 transition-all hover:scale-105"
                    >
                      <Coins className="w-12 h-12" />
                      <span className="text-lg font-medium">摇第 {currentStep + 1} 爻</span>
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* 卦象结果 */}
          {mainGua && (
            <div className="mb-6">
              <h3 className="font-medium text-gray-800 mb-4">卦象解析</h3>
              
              <div className="bg-gradient-to-r from-yellow-50 to-orange-50 rounded-xl p-4 border border-yellow-200">
                <div className="flex items-center gap-4 mb-4">
                  <div className="text-6xl text-yellow-600">
                    {mainGua.number <= 8 ? '☰' : '☷'}
                  </div>
                  <div>
                    <h4 className="text-xl font-bold text-gray-800">
                      第 {mainGua.number} 卦 · {mainGua.name}
                    </h4>
                    <p className="text-sm text-gray-500">{mainGua.attributes}</p>
                  </div>
                </div>
                <p className="text-gray-700">{mainGua.description}</p>
              </div>

              {changeGua && (
                <div className="mt-4 flex items-center gap-2 text-gray-500">
                  <ChevronRight className="w-5 h-5" />
                  <span>变卦：第 {changeGua.number} 卦 · {changeGua.name}</span>
                </div>
              )}
            </div>
          )}

          {/* AI解卦 */}
          {mainGua && (
            <div className="mb-6">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium text-gray-800">AI解卦</h3>
                <button
                  onClick={handleAiAnalysis}
                  disabled={isAnalyzing}
                  className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
                >
                  {isAnalyzing ? (
                    <RefreshCw className="w-4 h-4 animate-spin" />
                  ) : (
                    <Wand2 className="w-4 h-4" />
                  )}
                  {isAnalyzing ? '分析中...' : '开始解卦'}
                </button>
              </div>
              
              {aiAnalysis && (
                <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
                  <div className="prose prose-sm" dangerouslySetInnerHTML={{ 
                    __html: aiAnalysis.replace(/\n/g, '<br>') 
                  }}></div>
                </div>
              )}
            </div>
          )}

          {/* 重置按钮 */}
          {mainGua && (
            <button
              onClick={reset}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 border border-gray-200 rounded-xl hover:bg-gray-50 text-gray-700"
            >
              <RefreshCw className="w-5 h-5" /> 重新卜卦
            </button>
          )}

          {/* 说明 */}
          {currentStep === 0 && !mainGua && (
            <div className="mt-6 p-4 bg-blue-50 rounded-xl">
              <div className="flex items-start gap-2">
                <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
                <div className="text-sm text-blue-800">
                  <p className="font-medium mb-2">卜卦说明</p>
                  <ul className="space-y-1 text-blue-700">
                    <li>• 周易卜卦采用传统六爻法，共摇六次</li>
                    <li>• 6为老阴（变阳），7为少阳，8为少阴，9为老阳（变阴）</li>
                    <li>• 老阴和老阳为变爻，会产生变卦</li>
                    <li>• AI解卦结合传统易学和现代AI技术</li>
                  </ul>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 右侧：历史记录 */}
        {showHistory && (
          <div className="w-80 border-l border-gray-200 p-4 overflow-auto bg-gray-50">
            <h3 className="font-medium text-gray-800 mb-4">卜卦历史</h3>
            {history.length === 0 ? (
              <p className="text-gray-400 text-center">暂无历史记录</p>
            ) : (
              <div className="space-y-3">
                {history.slice(0, 10).map((record, index) => (
                  <div key={index} className="p-3 bg-white rounded-lg border border-gray-200">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-2xl">☰</span>
                      <span className="font-medium text-gray-800">
                        {record.main_gua?.name || '未知卦'}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mb-1">
                      {record.question || '无问题'}
                    </p>
                    <p className="text-xs text-gray-400">
                      {new Date(record.created_at).toLocaleString()}
                    </p>
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

export default YijingPanel;
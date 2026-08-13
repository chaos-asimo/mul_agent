import { useState, useEffect } from 'react';
import { Video, Play, Trash2, Sparkles, Image, Zap } from 'lucide-react';

function VideoPanel() {
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [prompt, setPrompt] = useState('');
  const [imageUrl, setImageUrl] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [videoUrl, setVideoUrl] = useState('');
  const [videoPrompt, setVideoPrompt] = useState('');
  const [generatedVideos, setGeneratedVideos] = useState([]);

  useEffect(() => {
    loadModels();
    loadGeneratedVideos();
  }, []);

  const loadModels = async () => {
    try {
      const response = await fetch('/api/video/models');
      const result = await response.json();
      if (result.success && Array.isArray(result.models)) {
        setModels(result.models);
        if (result.models.length > 0) {
          setSelectedModel(result.models[0].id || result.models[0].name);
        }
      }
    } catch (error) {
      console.error('加载视频模型失败:', error);
    }
  };

  const loadGeneratedVideos = async () => {
    try {
      const response = await fetch('/api/video/history');
      const result = await response.json();
      if (result.success && Array.isArray(result.history)) {
        setGeneratedVideos(result.history);
      }
    } catch (error) {
      console.error('加载视频历史失败:', error);
    }
  };

  const optimizePrompt = () => {
    const optimized = `${prompt}，高质量，4K分辨率，专业电影级画质，流畅动画`;
    setPrompt(optimized);
  };

  const generateVideo = async () => {
    if (!prompt.trim()) {
      alert('请输入视频描述');
      return;
    }

    setIsGenerating(true);
    setVideoUrl('');

    try {
      const data = {
        model_name: selectedModel,
        prompt: prompt.trim(),
      };

      if (imageUrl.trim()) {
        data.image_url = imageUrl.trim();
      }

      const response = await fetch('/api/video/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });

      const result = await response.json();

      if (result.success) {
        setVideoUrl(result.video_url);
        setVideoPrompt(result.prompt || prompt);
        loadGeneratedVideos();
      } else {
        alert(`生成失败: ${result.message || '未知错误'}`);
      }
    } catch (error) {
      console.error('生成视频失败:', error);
      alert(`生成失败: ${error.message}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const clearForm = () => {
    setPrompt('');
    setImageUrl('');
    setVideoUrl('');
    setVideoPrompt('');
  };

  const deleteVideo = async (id) => {
    if (!confirm('确定删除此视频？')) return;
    try {
      const response = await fetch(`/api/video/delete/${id}`, { method: 'DELETE' });
      const result = await response.json();
      if (result.success) {
        loadGeneratedVideos();
      }
    } catch (error) {
      console.error('删除视频失败:', error);
    }
  };

  return (
    <div className="h-full flex flex-col bg-white p-4">
      {/* 顶部标题 */}
      <div className="flex items-center gap-2 mb-4">
        <Video className="w-6 h-6 text-purple-600" />
        <h2 className="text-lg font-semibold text-gray-800">视频生成模型</h2>
      </div>

      {/* 表单区域 */}
      <div className="bg-gray-50 rounded-xl p-4 mb-4">
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">选择模型</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
            >
              {models.map((model) => (
                <option key={model.id || model.name} value={model.id || model.name}>
                  {model.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">参考图片URL（可选）</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={imageUrl}
                onChange={(e) => setImageUrl(e.target.value)}
                placeholder="输入图片URL..."
                className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
              />
              <button className="px-3 py-2 border border-gray-200 rounded-lg hover:bg-gray-100">
                <Image className="w-5 h-5 text-gray-500" />
              </button>
            </div>
          </div>
        </div>

        <div className="mb-4">
          <div className="flex items-center justify-between mb-1">
            <label className="block text-sm font-medium text-gray-700">视频描述</label>
            <button
              onClick={optimizePrompt}
              className="flex items-center gap-1 px-3 py-1 text-xs text-blue-600 bg-blue-50 rounded-lg hover:bg-blue-100"
            >
              <Sparkles className="w-3 h-3" /> 优化提示词
            </button>
          </div>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="描述您想要生成的视频内容，例如：一只猫在草地上奔跑，阳光明媚，4K画质..."
            rows={4}
            className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none"
          />
          <p className="text-xs text-gray-500 mt-1">提示：按照 [主体] + [动作] + [场景] + [镜头运动] + [光线] + [风格] 的结构描述效果更好</p>
        </div>

        <div className="flex gap-3">
          <button
            onClick={generateVideo}
            disabled={isGenerating || !prompt.trim()}
            className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isGenerating ? (
              <>
                <Zap className="w-4 h-4 animate-pulse" /> 生成中...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" /> 生成视频
              </>
            )}
          </button>
          <button
            onClick={clearForm}
            className="flex items-center gap-2 px-4 py-2 border border-gray-200 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <Trash2 className="w-4 h-4 text-gray-500" /> 清空
          </button>
        </div>
      </div>

      {/* 预览区域 */}
      {videoUrl && (
        <div className="bg-gray-50 rounded-xl p-4 mb-4">
          <h3 className="text-sm font-medium text-gray-700 mb-3">生成结果</h3>
          <video
            src={videoUrl}
            controls
            className="w-full max-h-64 object-contain rounded-lg"
          />
          <p className="text-xs text-gray-500 mt-2">提示词：{videoPrompt}</p>
        </div>
      )}

      {/* 历史记录 */}
      <div className="flex-1 min-h-0">
        <h3 className="text-sm font-medium text-gray-700 mb-3">历史记录</h3>
        {generatedVideos.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-40 text-gray-400">
            <Video className="w-12 h-12 mb-3" />
            <p>暂无生成记录</p>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-3 overflow-y-auto max-h-64">
            {generatedVideos.map((video) => (
              <div key={video.id} className="relative border border-gray-200 rounded-lg overflow-hidden">
                <video
                  src={video.video_url}
                  controls
                  className="w-full h-24 object-contain"
                />
                <div className="absolute top-1 right-1">
                  <button
                    onClick={() => deleteVideo(video.id)}
                    className="p-1 bg-black bg-opacity-50 text-white rounded hover:bg-red-600"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
                <p className="text-xs text-gray-500 p-2 truncate">{video.prompt}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default VideoPanel;
import { useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import { Brain, Save, Download, User, LogOut, FileText, Coins, MessageSquare, Video, Cog, Users, Search, Wand2, BarChart3, FileCode } from 'lucide-react';
import LobsterClawPanel from './panels/LobsterClawPanel';
import DocumentPanel from './panels/DocumentPanel';
import YijingPanel from './panels/YijingPanel';
import AIChatPanel from './panels/AIChatPanel';
import VideoPanel from './panels/VideoPanel';
import ModelsPanel from './panels/ModelsPanel';
import AgentsPanel from './panels/AgentsPanel';
import SearchPanel from './panels/SearchPanel';
import SkillsPanel from './panels/SkillsPanel';
import StatisticsPanel from './panels/StatisticsPanel';

const navItems = [
 { id: 'lobster-claw', icon: Brain, label: '龙虾Claw', color: 'text-orange-500' },
 { id: 'main', icon: FileText, label: '文档处理', color: 'text-blue-500' },
 { id: 'yijing', icon: Coins, label: '周易卜卦', color: 'text-yellow-500' },
 { id: 'ai-chat', icon: MessageSquare, label: 'AI聊天', color: 'text-green-500' },
 { id: 'video-models', icon: Video, label: '视频模型', color: 'text-purple-500' },
 { id: 'models', icon: Cog, label: '模型配置', color: 'text-gray-500' },
 { id: 'agents', icon: Users, label: 'Agent配置', color: 'text-cyan-500' },
 { id: 'search', icon: Search, label: '搜索引擎', color: 'text-pink-500' },
 { id: 'skills', icon: Wand2, label: 'Skills', color: 'text-indigo-500' },
 { id: 'statistics', icon: BarChart3, label: '统计分析', color: 'text-teal-500' },
];

function Layout() {
 const { logout, user } = useAuthStore();
 const [activeTab, setActiveTab] = useState('lobster-claw');
 const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

 const handleLogout = async () => {
 await logout();
 window.location.href = '/v2/login';
 };

 const renderPanel = () => {
 switch (activeTab) {
 case 'lobster-claw':
 return <LobsterClawPanel />;
 case 'main':
 return <DocumentPanel />;
 case 'yijing':
 return <YijingPanel />;
 case 'ai-chat':
 return <AIChatPanel />;
 case 'video-models':
 return <VideoPanel />;
 case 'models':
 return <ModelsPanel />;
 case 'agents':
 return <AgentsPanel />;
 case 'search':
 return <SearchPanel />;
 case 'skills':
 return <SkillsPanel />;
 case 'statistics':
 return <StatisticsPanel />;
 default:
 return <LobsterClawPanel />;
 }
 };

 return (<div className="flex flex-col h-screen bg-gray-100">
 {/* 顶部导航栏 */}
 <header className="bg-white border-b border-gray-200 shadow-sm">
 <div className="flex items-center justify-between px-4 py-3">
 <div className="flex items-center gap-3">
 <div className="flex items-center gap-2">
 <Brain className="w-6 h-6 text-blue-600"/>
 <span className="text-lg font-bold text-gray-800">多智能体协作平台</span>
 </div>
 </div>
 
 <div className="flex items-center gap-4">
 <button className="flex items-center gap-2 px-3 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
 <Save className="w-4 h-4"/>
 <span className="text-sm">保存文档</span>
 </button>
 <button className="flex items-center gap-2 px-3 py-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
 <Download className="w-4 h-4"/>
 <span className="text-sm">导出日志</span>
 </button>
 <div className="flex items-center gap-2 px-3 py-2 bg-blue-50 rounded-lg">
 <User className="w-4 h-4 text-blue-600"/>
 <span className="text-sm font-medium text-blue-600">
 {user?.username || ''}
 </span>
 </div>
 <button onClick={handleLogout} className="flex items-center gap-2 px-3 py-2 text-red-600 hover:bg-red-50 rounded-lg transition-colors">
 <LogOut className="w-4 h-4"/>
 <span className="text-sm">退出</span>
 </button>
 </div>
 </div>
 </header>

 {/* 主体内容区域 */}
 <div className="flex flex-1 overflow-hidden">
 {/* 左侧图标导航 */}
 <nav className={`bg-white border-r border-gray-200 flex flex-col items-center py-4 transition-all duration-300 ${sidebarCollapsed ? 'w-16' : 'w-20'}`}>
 {navItems.map((item) => {
 const Icon = item.icon;
 const isActive = activeTab === item.id;
 return (<button key={item.id} onClick={() => setActiveTab(item.id)} className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all duration-200 mb-2 ${isActive
 ? 'bg-blue-50 text-blue-600 shadow-sm'
 : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50'}`} title={item.label}>
 <Icon className="w-6 h-6"/>
 </button>);
 })}
 </nav>

 {/* 右侧工作区 */}
 <main className="flex-1 overflow-auto">
 {renderPanel()}
 </main>
 </div>
 </div>);
}

export default Layout;

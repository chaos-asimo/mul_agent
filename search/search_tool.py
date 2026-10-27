"""独立的搜索工具模块，提供可随时调用的搜索功能"""
import asyncio
import re
from typing import List, Dict, Any, Optional
import aiohttp


# ---- 搜索红线：政治敏感内容拦截 ----
# 命中以下关键词（不区分大小写）的搜索查询直接拒绝，不返回任何结果。
# 用户可在此处维护敏感词列表。
POLITICAL_SENSITIVE_KEYWORDS = [
    # 中文政治敏感词
    "政治", "政府", "总统", "主席", "总理", "首相", "议员", "议会",
    "共产党", "国民党", "民进党", "台独", "港独", "藏独", "疆独",
    "台湾", "独立", "分裂", "颠覆", "叛乱", "暴动", "政变", "革命",
    "国家主席", "国务院", "中央军委", "中央政治局", "人大", "政协",
    "选举", "投票", "竞选", "政党", "左派", "右派", "极左", "极右",
    "民主运动", "自由运动", "维权", "上访", "抗议", "游行", "示威",
    "恐怖主义", "基地组织", "ISIS", "塔利班", "极端组织",
    "战争", "军事", "核武器", "导弹", "战斗机", "航母", "军火",
    "间谍", "情报机构", "CIA", "FBI", "中情局", "克格勃",
    "外交部", "国防部", "安全局", "国安", "纪委", "监委",
    "领土", "主权", "边界", "国界", "争端", "冲突",
    "敏感", "违禁", "审查", "禁令", "封锁",
    # 英文政治敏感词（多词组需空格匹配，单词需词边界匹配）
    "politics", "political", "government", "president",
    "prime minister", "congress", "parliament", "senate",
    "house of representatives", "election", "voting",
    "leftist", "rightist", "terror", "terrorism", "military",
    "nuclear", "missile", "spy", "intelligence agency",
    "NSA", "sovereignty", "territory", "border dispute",
    "coup", "insurrection", "rebellion", "revolution",
    "communist", "nationalist", "separatist",
    "protest", "demonstration", "riot", "uprising",
]

# 英文单词需词边界匹配（避免 "war" 匹配到 "warcraft"），
# 中文关键词用子串匹配（Python \b 对中文无效），
# 多词短语按空格字面匹配。
def _build_pattern(keywords):
    parts = []
    for kw in keywords:
        escaped = re.escape(kw)
        if " " in escaped:
            parts.append(escaped)
        elif re.search(r"[a-zA-Z]", kw):
            parts.append(rf"\b{escaped}\b")
        else:
            parts.append(escaped)
    return re.compile("|".join(parts), re.IGNORECASE)

_POLITICAL_PATTERN = _build_pattern(POLITICAL_SENSITIVE_KEYWORDS)


def is_political_sensitive(query: str) -> bool:
    """检查搜索查询是否涉及政治敏感内容。命中则返回 True。"""
    if not query:
        return False
    return bool(_POLITICAL_PATTERN.search(query))


class SearchResult:
    """搜索结果"""
    def __init__(self, title: str, url: str, content: str):
        self.title = title
        self.url = url
        self.content = content
    
    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "content": self.content
        }


class TavilySearcher:
    """Tavily搜索工具"""
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.api_url = "https://api.tavily.com/search"
    
    async def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        """
        执行搜索
        
        Args:
            query: 搜索关键词
            num_results: 返回结果数量，默认5条
            
        Returns:
            搜索结果列表
        """
        if not self.api_key:
            return [SearchResult("Tavily未配置", "", "请配置Tavily API密钥")]
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "query": query,
                "max_results": num_results
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []
                        for item in data.get("results", [])[:num_results]:
                            results.append(SearchResult(
                                title=item.get("title", ""),
                                url=item.get("url", ""),
                                content=item.get("content", "")
                            ))
                        return results
                    elif response.status == 401:
                        return [SearchResult("API认证失败", "", "API密钥无效或已过期")]
                    else:
                        error_text = await response.text()
                        return [SearchResult(f"搜索失败({response.status})", "", error_text[:200])]
                        
        except asyncio.TimeoutError:
            return [SearchResult("搜索超时", "", "请求超时，请稍后重试")]
        except Exception as e:
            return [SearchResult("搜索异常", "", str(e))]
    
    async def search_sync(self, query: str, num_results: int = 5) -> List[Dict[str, str]]:
        """
        同步接口，返回字典格式的结果
        """
        results = await self.search(query, num_results)
        return [r.to_dict() for r in results]


class SearchTool:
    """统一的搜索工具接口"""
    
    def __init__(self, api_key: str = "", search_type: str = "tavily"):
        self.search_type = search_type
        self.api_key = api_key
        
        if search_type == "tavily":
            self.searcher = TavilySearcher(api_key)
        else:
            self.searcher = TavilySearcher(api_key)  # 默认使用Tavily
    
    async def search(self, query: str, num_results: int = 5) -> List[SearchResult]:
        """执行搜索（含政治敏感拦截）"""
        if is_political_sensitive(query):
            return [SearchResult("搜索被拦截", "", "查询涉及政治敏感内容，已被系统红线拦截")]
        results = await self.searcher.search(query, num_results)
        # 过滤结果中涉及政治敏感的新闻
        filtered = [r for r in results if not is_political_sensitive(f"{r.title} {r.content}")]
        if not filtered:
            return [SearchResult("无相关结果", "", "搜索结果涉及政治敏感内容，已按红线过滤")]
        return filtered

    async def search_for_context(self, query: str, num_results: int = 3) -> str:
        """
        搜索并返回格式化的上下文字符串（含政治敏感拦截）
        
        Args:
            query: 搜索关键词
            num_results: 返回结果数量
            
        Returns:
            格式化的搜索结果字符串
        """
        if is_political_sensitive(query):
            return "[搜索被拦截] 查询涉及政治敏感内容，已被系统红线拦截"
        results = await self.search(query, num_results)
        
        if not results:
            return ""
        
        context_parts = []
        for i, result in enumerate(results, 1):
            if result.title and result.content:
                context_parts.append(f"{i}. {result.title}")
                context_parts.append(f"   来源: {result.url}")
                context_parts.append(f"   摘要: {result.content[:300]}...")
                context_parts.append("")
        
        return "\n".join(context_parts)


# 全局搜索工具实例
_search_tool: Optional[SearchTool] = None


def get_search_tool(api_key: str = "", search_type: str = "tavily") -> SearchTool:
    """获取搜索工具实例"""
    global _search_tool
    if _search_tool is None or api_key:
        _search_tool = SearchTool(api_key=api_key, search_type=search_type)
    return _search_tool


async def quick_search(query: str, api_key: str = "", num_results: int = 5) -> List[Dict[str, str]]:
    """
    快速搜索函数，随时调用
    
    Args:
        query: 搜索关键词
        api_key: Tavily API密钥（可选，如果不提供则使用全局配置）
        num_results: 返回结果数量
        
    Returns:
        搜索结果列表，每条结果包含 title, url, content
        若查询涉及政治敏感内容，返回一条拦截提示。
    """
    if is_political_sensitive(query):
        return [{
            "title": "搜索被拦截",
            "url": "",
            "content": "查询涉及政治敏感内容，已被系统红线拦截，无法提供搜索结果。",
        }]
    tool = get_search_tool(api_key)
    results = await tool.search(query, num_results)
    # 过滤结果中涉及政治敏感的新闻
    filtered = [
        r for r in results
        if not is_political_sensitive(f"{r.title} {r.content}")
    ]
    if not filtered:
        return [{
            "title": "无相关结果",
            "url": "",
            "content": "搜索结果涉及政治敏感内容，已按红线过滤，无其他可展示内容。",
        }]
    return [r.to_dict() for r in filtered]


async def quick_search_context(query: str, api_key: str = "", num_results: int = 3) -> str:
    """
    快速搜索并返回格式化上下文
    
    Args:
        query: 搜索关键词
        api_key: Tavily API密钥
        num_results: 返回结果数量
        
    Returns:
        格式化后的搜索结果字符串
        若查询涉及政治敏感内容，返回拦截提示。
    """
    if is_political_sensitive(query):
        return "[搜索被拦截] 查询涉及政治敏感内容，已被系统红线拦截，无法提供搜索结果。"
    tool = get_search_tool(api_key)
    results = await tool.search(query, num_results)
    # 过滤结果中涉及政治敏感的新闻
    filtered = [
        r for r in results
        if not is_political_sensitive(f"{r.title} {r.content}")
    ]
    if not filtered:
        return "[无相关结果] 搜索结果涉及政治敏感内容，已按红线过滤，无其他可展示内容。"
    context_parts = []
    for i, result in enumerate(filtered, 1):
        if result.title and result.content:
            context_parts.append(f"{i}. {result.title}")
            context_parts.append(f"   来源: {result.url}")
            context_parts.append(f"   摘要: {result.content[:300]}...")
            context_parts.append("")
    return "\n".join(context_parts)

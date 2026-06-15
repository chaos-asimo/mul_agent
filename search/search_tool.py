"""独立的搜索工具模块，提供可随时调用的搜索功能"""
import asyncio
from typing import List, Dict, Any, Optional
import aiohttp


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
        """执行搜索"""
        return await self.searcher.search(query, num_results)
    
    async def search_for_context(self, query: str, num_results: int = 3) -> str:
        """
        搜索并返回格式化的上下文字符串
        
        Args:
            query: 搜索关键词
            num_results: 返回结果数量
            
        Returns:
            格式化的搜索结果字符串
        """
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
    """
    tool = get_search_tool(api_key)
    results = await tool.search(query, num_results)
    return [r.to_dict() for r in results]


async def quick_search_context(query: str, api_key: str = "", num_results: int = 3) -> str:
    """
    快速搜索并返回格式化上下文
    
    Args:
        query: 搜索关键词
        api_key: Tavily API密钥
        num_results: 返回结果数量
        
    Returns:
        格式化后的搜索结果字符串
    """
    tool = get_search_tool(api_key)
    return await tool.search_for_context(query, num_results)

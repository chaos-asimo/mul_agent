"""Base adapter for search engines"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import aiohttp
import asyncio


@dataclass
class SearchResult:
    """Search result container"""
    title: str
    url: str
    snippet: str
    source: str = ""


class SearchAdapter(ABC):
    """Abstract base class for search adapters"""

    def __init__(self, api_key: str = "", api_url: str = ""):
        self.api_key = api_key
        self.api_url = api_url

    @abstractmethod
    async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
        """Perform search and return results"""
        pass

    @abstractmethod
    def get_source_name(self) -> str:
        """Return the name of the search source"""
        pass

    def _create_result(self, title: str, url: str, snippet: str) -> SearchResult:
        """Create a search result"""
        return SearchResult(
            title=title,
            url=url,
            snippet=snippet,
            source=self.get_source_name()
        )


class BingAdapter(SearchAdapter):
    """Bing Search API adapter"""

    def __init__(self, api_key: str = "", api_url: str = ""):
        super().__init__(api_key, api_url or "https://api.bing.microsoft.com/v7.0/search")

    async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
        """Search using Bing API"""
        if not self.api_key:
            return [self._create_result(
                "Bing搜索未配置",
                "",
                "请在搜索引擎配置页面配置Bing API密钥"
            )]

        try:
            headers = {"Ocp-Apim-Subscription-Key": self.api_key}
            params = {"q": query, "count": num_results, "mkt": "zh-CN"}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.api_url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []
                        for item in data.get("webPages", {}).get("value", [])[:num_results]:
                            results.append(self._create_result(
                                item.get("name", ""),
                                item.get("url", ""),
                                item.get("snippet", "")
                            ))
                        return results
                    else:
                        return [self._create_result(
                            "Bing API错误",
                            "",
                            f"状态码: {response.status}"
                        )]
        except asyncio.TimeoutError:
            return [self._create_result("Bing搜索超时", "", "请求超时，请稍后重试")]
        except Exception as e:
            return [self._create_result("Bing搜索失败", "", str(e))]

    def get_source_name(self) -> str:
        return "Bing搜索"


class GoogleAdapter(SearchAdapter):
    """Google Search API adapter (using SerpAPI or custom)"""

    def __init__(self, api_key: str = "", api_url: str = ""):
        super().__init__(api_key, api_url or "https://serpapi.com/search")

    async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
        """Search using Google/SerpAPI"""
        if not self.api_key:
            return [self._create_result(
                "Google搜索未配置",
                "",
                "请在搜索引擎配置页面配置SerpAPI密钥"
            )]

        try:
            params = {
                "q": query,
                "api_key": self.api_key,
                "num": num_results
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.api_url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []
                        for item in data.get("organic_results", [])[:num_results]:
                            results.append(self._create_result(
                                item.get("title", ""),
                                item.get("link", ""),
                                item.get("snippet", "")
                            ))
                        return results
                    else:
                        return [self._create_result(
                            "Google API错误",
                            "",
                            f"状态码: {response.status}"
                        )]
        except asyncio.TimeoutError:
            return [self._create_result("Google搜索超时", "", "请求超时，请稍后重试")]
        except Exception as e:
            return [self._create_result("Google搜索失败", "", str(e))]

    def get_source_name(self) -> str:
        return "Google搜索"


class BaiduAdapter(SearchAdapter):
    """Baidu Search API adapter"""

    def __init__(self, api_key: str = "", api_url: str = ""):
        super().__init__(api_key, api_url or "https://api.baidu.com/json/sms/v3/search")

    async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
        """Search using Baidu API"""
        if not self.api_key:
            return [self._create_result(
                "百度搜索未配置",
                "",
                "请在搜索引擎配置页面配置百度API密钥"
            )]

        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            params = {"query": query, "page_size": num_results}

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.api_url,
                    headers=headers,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []
                        for item in data.get("results", [])[:num_results]:
                            results.append(self._create_result(
                                item.get("title", ""),
                                item.get("url", ""),
                                item.get("abstract", "")
                            ))
                        return results
                    else:
                        return [self._create_result(
                            "百度API错误",
                            "",
                            f"状态码: {response.status}"
                        )]
        except asyncio.TimeoutError:
            return [self._create_result("百度搜索超时", "", "请求超时，请稍后重试")]
        except Exception as e:
            return [self._create_result("百度搜索失败", "", str(e))]

    def get_source_name(self) -> str:
        return "百度搜索"


class TavilyAdapter(SearchAdapter):
    """Tavily Search API adapter"""

    def __init__(self, api_key: str = "", api_url: str = ""):
        super().__init__(api_key, api_url or "https://api.tavily.com/search")

    async def search(self, query: str, num_results: int = 10) -> List[SearchResult]:
        """Search using Tavily API"""
        if not self.api_key:
            return [self._create_result(
                "Tavily搜索未配置",
                "",
                "请在搜索引擎配置页面配置Tavily API密钥"
            )]

        try:
            headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
            payload = {
                "query": query,
                "max_results": num_results
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = []
                        for item in data.get("results", [])[:num_results]:
                            results.append(self._create_result(
                                item.get("title", ""),
                                item.get("url", ""),
                                item.get("content", "")
                            ))
                        return results
                    elif response.status == 401:
                        return [self._create_result(
                            "Tavily API认证失败",
                            "",
                            "API密钥无效或已过期，请访问 https://app.tavily.com/ 获取有效的API密钥"
                        )]
                    else:
                        try:
                            error_data = await response.json()
                            error_msg = error_data.get("error", {}).get("message", f"状态码: {response.status}")
                        except:
                            error_msg = f"状态码: {response.status}"
                        return [self._create_result(
                            "Tavily API错误",
                            "",
                            error_msg
                        )]
        except asyncio.TimeoutError:
            return [self._create_result("Tavily搜索超时", "", "请求超时，请稍后重试")]
        except Exception as e:
            return [self._create_result("Tavily搜索失败", "", str(e))]

    def get_source_name(self) -> str:
        return "Tavily搜索"


def create_adapter(adapter_type: str, api_key: str = "", api_url: str = "") -> Optional[SearchAdapter]:
    """Factory function to create search adapter"""
    adapters = {
        "bing": BingAdapter,
        "google": GoogleAdapter,
        "baidu": BaiduAdapter,
        "tavily": TavilyAdapter
    }
    adapter_class = adapters.get(adapter_type.lower())
    if adapter_class:
        return adapter_class(api_key, api_url)
    return None

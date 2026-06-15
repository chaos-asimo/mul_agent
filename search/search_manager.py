"""Search engine manager"""
import json
import os
import asyncio
from typing import List, Optional, Dict
from .search_config import SearchEngineConfig
from .search_adapters import SearchAdapter, create_adapter, SearchResult


class SearchManager:
    """Manages search engine configurations and operations"""

    DEFAULT_SEARCH_ENGINES = [
        SearchEngineConfig(
            id="default_bing",
            name="Bing搜索",
            adapter_type="bing",
            api_key="",
            api_url="",
            enabled=True
        ),
        SearchEngineConfig(
            id="default_google",
            name="Google搜索",
            adapter_type="google",
            api_key="",
            api_url="",
            enabled=True
        ),
        SearchEngineConfig(
            id="default_baidu",
            name="百度搜索",
            adapter_type="baidu",
            api_key="",
            api_url="",
            enabled=True
        ),
    ]

    def __init__(self, config_path: str = "search_engines.json"):
        self.config_path = config_path
        self.search_engines: List[SearchEngineConfig] = []
        self.adapters: Dict[str, SearchAdapter] = {}
        self.load()

    def load(self):
        """Load search engines from file or create defaults"""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.search_engines = [SearchEngineConfig.from_dict(s) for s in data]
                self._update_adapters()
                return
            except (json.JSONDecodeError, KeyError):
                pass
        self.search_engines = self.DEFAULT_SEARCH_ENGINES.copy()
        self.save()
        self._update_adapters()

    def save(self):
        """Save search engines to file"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump([s.to_dict() for s in self.search_engines], f, ensure_ascii=False, indent=2)

    def _update_adapters(self):
        """Update adapter instances"""
        self.adapters.clear()
        for config in self.search_engines:
            adapter = create_adapter(config.adapter_type, config.api_key, config.api_url)
            if adapter:
                self.adapters[config.id] = adapter

    def add(self, config: SearchEngineConfig) -> bool:
        """Add a new search engine"""
        if any(s.id == config.id for s in self.search_engines):
            return False
        self.search_engines.append(config)
        self._update_adapters()
        self.save()
        return True

    def update(self, config: SearchEngineConfig) -> bool:
        """Update an existing search engine"""
        for i, s in enumerate(self.search_engines):
            if s.id == config.id:
                self.search_engines[i] = config
                self._update_adapters()
                self.save()
                return True
        return False

    def delete(self, search_id: str) -> bool:
        """Delete a search engine"""
        for i, s in enumerate(self.search_engines):
            if s.id == search_id:
                del self.search_engines[i]
                self._update_adapters()
                self.save()
                return True
        return False

    def get(self, search_id: str) -> Optional[SearchEngineConfig]:
        """Get a search engine by ID"""
        for s in self.search_engines:
            if s.id == search_id:
                return s
        return None

    def get_all(self) -> List[SearchEngineConfig]:
        """Get all search engines"""
        return self.search_engines.copy()

    def get_enabled(self) -> List[SearchEngineConfig]:
        """Get enabled search engines"""
        return [s for s in self.search_engines if s.enabled]

    async def search(self, query: str, search_engine_id: str = None, num_results: int = 5) -> List[SearchResult]:
        """Perform search using specified or first available engine"""
        if search_engine_id:
            adapter = self.adapters.get(search_engine_id)
            if adapter:
                return await adapter.search(query, num_results)
        else:
            # Use first enabled search engine
            for config in self.get_enabled():
                adapter = self.adapters.get(config.id)
                if adapter:
                    return await adapter.search(query, num_results)

        return [SearchResult(
            title="无可用搜索引擎",
            url="",
            snippet="请在设置中配置至少一个搜索引擎API"
        )]

    def search_sync(self, query: str, search_engine_id: str = None, num_results: int = 5) -> List[SearchResult]:
        """Synchronous wrapper for search"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new loop if current one is running
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(self.search(query, search_engine_id, num_results))
            else:
                return loop.run_until_complete(self.search(query, search_engine_id, num_results))
        except Exception:
            # Fallback for older Python versions
            try:
                return asyncio.run(self.search(query, search_engine_id, num_results))
            except Exception:
                return [SearchResult(
                    title="搜索失败",
                    url="",
                    snippet="无法执行搜索操作"
                )]

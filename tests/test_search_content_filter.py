# -*- coding: utf-8 -*-
"""搜索内容红线过滤逻辑单元测试

覆盖 search/search_tool.py 中的：
- is_political_sensitive
- is_pornography
- is_terrorism
- is_content_violation

运行: python -B -m pytest tests/test_search_content_filter.py -v
或:   python -B tests/test_search_content_filter.py
"""
import os
import sys
from typing import Callable, List

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from search.search_tool import (
    is_content_violation,
    is_political_sensitive,
    is_pornography,
    is_terrorism,
)


def test_empty_or_whitespace_like_input_is_safe():
    """空输入不应命中任何红线，避免把缺少 query 当成违规。"""
    assert is_content_violation("") is False
    assert is_political_sensitive("") is False
    assert is_pornography("") is False
    assert is_terrorism("") is False


def test_normal_queries_are_not_blocked():
    """普通生活、学习、技术类查询不应误拦。"""
    safe_queries = [
        "明天北京天气怎么样",
        "python 列表和元组有什么区别",
        "人工智能最新进展",
        "如何做红烧肉",
        "附近有什么好吃的餐馆",
    ]

    for query in safe_queries:
        assert is_content_violation(query) is False, query
        assert is_political_sensitive(query) is False, query
        assert is_pornography(query) is False, query
        assert is_terrorism(query) is False, query


def test_chinese_political_keyword_is_detected():
    """中文政治敏感词使用子串匹配。"""
    assert is_political_sensitive("最近的政府政策有什么变化")
    assert is_political_sensitive("关于选举的讨论")
    assert is_content_violation("关于选举的讨论")


def test_english_political_keyword_uses_word_boundary():
    """英文政治敏感词需要词边界匹配，避免误伤包含同字母的普通词。"""
    assert is_political_sensitive("latest political news")
    assert is_content_violation("latest political news")
    # "politics" 不应被包含在 "political" 里误判为单独命中政治词，
    # 但 "political" 本身已在政治敏感词中，因此这里只验证边界行为。
    assert not is_political_sensitive("politically")


def test_chinese_pornography_keywords_are_detected():
    """中文涉黄关键词命中时应返回 True。"""
    assert is_pornography("哪里可以看色情内容")
    assert is_pornography("寻找成人视频资源")
    assert is_pornography("这个网站有黄色网站入口吗")
    assert is_content_violation("哪里可以看色情内容")
    assert is_content_violation("寻找成人视频资源")


def test_english_pornography_keywords_are_detected():
    """英文涉黄关键词不区分大小写命中。"""
    assert is_pornography("find porn videos")
    assert is_pornography("Where can I watch XXX content")
    assert is_pornography("adult video sites")
    assert is_pornography("cam girl live")
    assert is_content_violation("find porn videos")


def test_pornography_keyword_uses_word_boundary_for_english():
    """英文单词关键词不应被更长单词误触发。"""
    assert not is_pornography("pornographer")
    assert not is_pornography("rapes")  # rape 不匹配 rapes
    assert is_pornography("rape")


def test_chinese_terrorism_keywords_are_detected():
    """中文涉恐关键词命中时应返回 True。"""
    assert is_terrorism("如何实施恐怖袭击")
    assert is_terrorism("恐怖分子的组织结构")
    assert is_terrorism("自制炸弹的制作方法")
    assert is_content_violation("如何实施恐怖袭击")
    assert is_content_violation("恐怖分子的组织结构")


def test_english_terrorism_keywords_are_detected():
    """英文涉恐关键词命中时应返回 True。"""
    assert is_terrorism("how to make a bomb making device")
    assert is_terrorism("suicide attack news")
    assert is_terrorism("lone wolf attack")
    assert is_terrorism("TERRORIST attack")
    assert is_content_violation("suicide attack news")


def test_english_terrorism_keyword_uses_word_boundary():
    """英文涉恐单词需要词边界匹配，避免误伤包含关键词字母的普通词。"""
    assert not is_terrorism("hijackers")  # hijack 不匹配 hijackers
    assert is_terrorism("hijack")
    assert not is_terrorism("kidnapped")
    assert is_terrorism("kidnap")


def test_multilingual_mixed_query_hits_when_any_category_matches():
    """中英混合 query 只要命中任一红线就应拦截。"""
    assert is_content_violation("我想了解 porn 和 terrorism")
    assert is_content_violation("government 相关的 porn 资源")
    assert is_content_violation("恐怖分子和 选举")


def test_result_text_filtering_uses_same_rules():
    """模拟结果标题+内容过滤：只有结果文本命中才过滤。"""
    clean_result = "今天科技新闻摘要"
    blocked_result = "成人视频资源汇总"

    assert not is_content_violation(clean_result)
    assert is_content_violation(blocked_result)


def _run_tests() -> None:
    tests: List[Callable[[], None]] = [
        test_empty_or_whitespace_like_input_is_safe,
        test_normal_queries_are_not_blocked,
        test_chinese_political_keyword_is_detected,
        test_english_political_keyword_uses_word_boundary,
        test_chinese_pornography_keywords_are_detected,
        test_english_pornography_keywords_are_detected,
        test_pornography_keyword_uses_word_boundary_for_english,
        test_chinese_terrorism_keywords_are_detected,
        test_english_terrorism_keywords_are_detected,
        test_english_terrorism_keyword_uses_word_boundary,
        test_multilingual_mixed_query_hits_when_any_category_matches,
        test_result_text_filtering_uses_same_rules,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} tests passed")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    _run_tests()

"""模型首字输出速度（TTFT）统计与排序

从 model_call_logger 的内存日志中，按模型聚合最近 N 次成功调用的首字耗时平均值，
升序排序（最快在前），用于动态选择最快的默认模型。
"""
from collections import defaultdict
from typing import List, Dict, Optional

from llm.model_call_logger import model_call_logger


def get_model_speed_ranking(recent_n: int = 20) -> List[Dict]:
    """返回各文本模型的首字速度排名（升序，TTFT 越小越快）。

    每条记录结构: {model_name, avg_ttft, sample_count, last_ttft}
    仅统计成功（无 error）且有有效 ttft（>0）的调用。
    """
    # 按模型收集 ttft（call_logs 已按时间升序，直接分组保留顺序）
    bucket: Dict[str, List[float]] = defaultdict(list)
    for log in model_call_logger.call_logs:
        if log.error or not log.ttft or log.ttft <= 0:
            continue
        bucket[log.model_name].append(log.ttft)

    ranking = []
    for model_name, ttfts in bucket.items():
        recent = ttfts[-recent_n:]  # 最近 N 次
        if not recent:
            continue
        ranking.append({
            "model_name": model_name,
            "avg_ttft": round(sum(recent) / len(recent), 4),
            "sample_count": len(recent),
            "last_ttft": round(recent[-1], 4),
        })
    ranking.sort(key=lambda x: x["avg_ttft"])
    return ranking


def get_fastest_model_id(
    candidate_model_names: List[str],
    recent_n: int = 20,
) -> Optional[str]:
    """从候选模型名中，选出首字速度最快的模型名。

    candidate_model_names: 有资格成为默认的模型（如已配置 api_key 的文本模型）。
    若所有候选都无速度数据，返回 None（调用方保持原默认不变）。
    """
    if not candidate_model_names:
        return None
    ranking = {r["model_name"]: r["avg_ttft"] for r in get_model_speed_ranking(recent_n)}
    # 只在候选范围内、且有统计数据的模型中选最快
    best = None
    best_ttft = None
    for name in candidate_model_names:
        ttft = ranking.get(name)
        if ttft is None:
            continue
        if best_ttft is None or ttft < best_ttft:
            best_ttft = ttft
            best = name
    return best


def apply_fastest_default() -> Optional[str]:
    """将首字速度最快的文本模型设为全局默认（移到 models.json 列表首位）。

    返回被设为默认的模型名；无速度数据或已是最快时返回 None（不改动）。
    """
    try:
        from models.model_manager import ModelManager
        mm = ModelManager()
        models = mm.models
        text_models = [m for m in models if m.api_key and m.model_type == "text"]
        if not text_models:
            return None
        fastest = get_fastest_model_id([m.model_name for m in text_models])
        if not fastest:
            return None  # 无统计数据，保持原状
        if text_models[0].model_name == fastest:
            return None  # 当前默认已是最快
        # 把最快模型移到列表最前，其余保持相对顺序
        fastest_model = next((m for m in models if m.model_name == fastest), None)
        if fastest_model is None:
            return None
        models.remove(fastest_model)
        models.insert(0, fastest_model)
        mm.save()
        return fastest
    except Exception as e:
        print(f"[model_speed] apply_fastest_default 失败: {e}")
        return None

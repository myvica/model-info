from __future__ import annotations

from typing import Any, Dict, List


def _uniq_list(xs: List[Any]) -> List[Any]:
    seen = set()
    out: List[Any] = []
    for x in xs:
        k = str(x)
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out


def merge_model_info(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
    """
    one-hub 的 model_info 合并策略（尽量补齐，不覆盖已有更“实”的值）。
    - list 字段：并集去重
    - 数字字段：dst 为 0/空时，用 src 补齐
    - 字符串字段：dst 为空时，用 src 补齐
    """
    out = dict(dst or {})
    for k, v in (src or {}).items():
        if v is None:
            continue

        if isinstance(v, list):
            out[k] = _uniq_list(list(out.get(k) or []) + list(v))
            continue

        if isinstance(v, (int, float)):
            if out.get(k) in (None, 0, 0.0, "") and v not in (None, 0, 0.0, ""):
                out[k] = v
            continue

        # string / object
        if out.get(k) in (None, "") and v not in (None, ""):
            out[k] = v

    return out


def merge_items(*sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    以 model 为主键合并多来源 items：
    item: { "model": "...", "model_info": {...} }
    """
    by_model: Dict[str, Dict[str, Any]] = {}
    for items in sources:
        for it in items or []:
            if not isinstance(it, dict):
                continue
            model = (it or {}).get("model")
            if not model:
                continue
            cur = by_model.get(model) or {"model": model, "model_info": {}}
            cur["model_info"] = merge_model_info(
                cur.get("model_info") or {}, (it.get("model_info") or {})
            )
            by_model[model] = cur
    return sorted(by_model.values(), key=lambda x: x["model"])


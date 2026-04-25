from __future__ import annotations

from typing import Any, Dict, Tuple

import requests


LITELLM_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"


def fetch(timeout_s: int = 60) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    LiteLLM：公开维护的模型能力/上下文/特性清单（JSON）。

    注意：该 JSON 非 onehub 结构，而是 dict[model_name] -> spec。
    我们在 generate.py 中只对现有模型做“精确匹配补全”，不会把 LiteLLM 全量模型加入输出。
    """
    headers = {
        "User-Agent": "onehub-modelinfo-pages/1.0 (+https://github.com/)",
        "Accept": "application/json",
    }
    r = requests.get(LITELLM_URL, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    j = r.json()
    # 丢弃 sample_spec（不是模型条目）
    if isinstance(j, dict) and "sample_spec" in j:
        j.pop("sample_spec", None)

    meta = {
        "name": "litellm",
        "url": LITELLM_URL,
        "note": "public JSON; used only to enrich existing models by exact name match",
    }
    return (j if isinstance(j, dict) else {}), meta


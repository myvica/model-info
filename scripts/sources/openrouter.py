from __future__ import annotations

from typing import Any, Dict, List, Tuple

import requests


OPENROUTER_URL = "https://openrouter.ai/api/v1/models?output_modalities=all"


def fetch(timeout_s: int = 30) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    OpenRouter：公开 Models API。
    - 仅保留 id 以 :free 结尾的模型（用户需求：只要 free）
    """
    headers = {
        "User-Agent": "onehub-modelinfo-pages/1.0 (+https://github.com/)",
        "Accept": "application/json",
    }
    r = requests.get(OPENROUTER_URL, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    j = r.json()
    data = j.get("data") or []

    items: List[Dict[str, Any]] = []
    for m in data:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if not isinstance(mid, str) or not mid.endswith(":free"):
            continue

        # best-effort 输出模态
        modalities: List[str] = []
        # OpenRouter 字段可能变化，这里用“尽力而为”的兜底逻辑
        for key in ("output_modalities", "modalities", "supported_output_modalities"):
            v = m.get(key)
            if isinstance(v, list) and v:
                modalities = [str(x) for x in v if x]
                break
        if not modalities:
            modalities = ["text"]

        desc = ""
        if isinstance(m.get("description"), str):
            desc = m["description"]
        elif isinstance(m.get("name"), str):
            desc = m["name"]

        mi: Dict[str, Any] = {
            "description": desc,
            "modalities": modalities,
            "tags": ["free", "openrouter"],
        }

        # context_length best-effort
        for key in ("context_length", "context", "max_context_length", "max_tokens"):
            v = m.get(key)
            if isinstance(v, int) and v > 0:
                mi["context_length"] = v
                break

        items.append({"model": mid, "model_info": mi})

    meta = {
        "name": "openrouter",
        "url": OPENROUTER_URL,
        "note": "free-only by suffix :free",
    }
    return items, meta


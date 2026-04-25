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

        name = m.get("name") if isinstance(m.get("name"), str) else mid
        desc = m.get("description") if isinstance(m.get("description"), str) else ""

        arch = m.get("architecture") if isinstance(m.get("architecture"), dict) else {}
        input_mods = arch.get("input_modalities") if isinstance(arch.get("input_modalities"), list) else []
        output_mods = arch.get("output_modalities") if isinstance(arch.get("output_modalities"), list) else []
        tokenizer = arch.get("tokenizer") if isinstance(arch.get("tokenizer"), str) else "Other"
        modality = arch.get("modality") if isinstance(arch.get("modality"), str) else ""

        context_len = m.get("context_length") if isinstance(m.get("context_length"), int) else 0
        top_provider = m.get("top_provider") if isinstance(m.get("top_provider"), dict) else {}
        if not context_len and isinstance(top_provider.get("context_length"), int):
            context_len = int(top_provider["context_length"])
        max_tokens = 0
        if isinstance(top_provider.get("max_completion_tokens"), int):
            max_tokens = int(top_provider["max_completion_tokens"])

        # 按需求：不输出 tokenizer:* 与 modality:* 这类 tags，仅保留基础分类
        tags = ["openrouter", "free"]

        mi: Dict[str, Any] = {
            "model": mid,
            "name": name,
            "description": desc,
            "context_length": context_len,
            "max_tokens": max_tokens,
            "input_modalities": [str(x) for x in input_mods if x],
            "output_modalities": [str(x) for x in output_mods if x],
            "tags": tags,
            "support_url": [f"https://openrouter.ai/{mid}"],
        }

        items.append({"model": mid, "model_info": mi})

    meta = {
        "name": "openrouter",
        "url": OPENROUTER_URL,
        "note": "free-only by suffix :free",
    }
    return items, meta

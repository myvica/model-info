from __future__ import annotations

from typing import Any, Dict, List, Tuple

import requests


POE_MODELS_URL = "https://api.poe.com/v1/models"


def fetch(timeout_s: int = 30) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Poe Models API（公开 JSON，无需 secrets）。

    输出 onehub 兼容 items：
      item: { "model": "...", "model_info": {...} }
    注意：这里返回“Poe 全量模型”；是否合并进总表由 generate.py 决定（总表只合并 output 含 text 的模型）。
    """
    headers = {
        "User-Agent": "onehub-modelinfo-pages/1.0 (+https://github.com/)",
        "Accept": "application/json",
    }
    r = requests.get(POE_MODELS_URL, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    j = r.json()

    data = j.get("data") if isinstance(j, dict) else []
    if not isinstance(data, list):
        data = []

    items: List[Dict[str, Any]] = []
    for m in data:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if not isinstance(mid, str) or not mid.strip():
            continue
        mid = mid.strip()

        arch = m.get("architecture") if isinstance(m.get("architecture"), dict) else {}
        in_mods = arch.get("input_modalities") if isinstance(arch.get("input_modalities"), list) else []
        out_mods = arch.get("output_modalities") if isinstance(arch.get("output_modalities"), list) else []

        # context window（best-effort）
        ctx_len = 0
        max_out = 0
        ctx = m.get("context_window") if isinstance(m.get("context_window"), dict) else {}
        if isinstance(ctx.get("context_length"), int):
            ctx_len = int(ctx["context_length"])
        elif isinstance(m.get("context_length"), int):
            ctx_len = int(m["context_length"])
        if isinstance(ctx.get("max_output_tokens"), int):
            max_out = int(ctx["max_output_tokens"])

        meta = m.get("metadata") if isinstance(m.get("metadata"), dict) else {}
        display_name = meta.get("display_name") if isinstance(meta.get("display_name"), str) else ""
        page_url = meta.get("url") if isinstance(meta.get("url"), str) else ""

        mi: Dict[str, Any] = {
            "model": mid,
            "name": display_name.strip() or mid,
            "description": m.get("description") if isinstance(m.get("description"), str) else "",
            "context_length": ctx_len,
            "max_tokens": max_out,
            "input_modalities": [str(x) for x in in_mods if x],
            "output_modalities": [str(x) for x in out_mods if x],
            "tags": ["poe"],
            "support_url": [page_url] if page_url else [POE_MODELS_URL],
        }

        items.append({"model": mid, "model_info": mi})

    meta_out = {"name": "poe", "url": POE_MODELS_URL, "note": "public models list (no auth)"}
    return items, meta_out


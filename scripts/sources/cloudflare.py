from __future__ import annotations

from typing import Any, Dict, List, Tuple

import requests


# Cloudflare 公开模型目录（无需 token）
CF_MODELS_URL = "https://ai-cloudflare-com.pages.dev/api/models"


def _get_prop(props: List[Dict[str, Any]], key: str) -> Any:
    for p in props or []:
        if isinstance(p, dict) and p.get("property_id") == key:
            return p.get("value")
    return None


def fetch(timeout_s: int = 30) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Cloudflare Models API（公开 JSON）。

    按用户确认：只保留 task.name == "Text Generation" 的模型，并输出为 onehub 兼容 items：
      item: { "model": "...", "model_info": {...} }
    """
    headers = {
        "User-Agent": "onehub-modelinfo-pages/1.0 (+https://github.com/)",
        "Accept": "application/json",
    }
    r = requests.get(CF_MODELS_URL, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    j = r.json()
    models = j.get("models") if isinstance(j, dict) else None
    if not isinstance(models, list):
        models = []

    items: List[Dict[str, Any]] = []
    for m in models:
        if not isinstance(m, dict):
            continue
        task = m.get("task") if isinstance(m.get("task"), dict) else {}
        task_name = task.get("name") if isinstance(task.get("name"), str) else ""
        if task_name != "Text Generation":
            continue

        name = m.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()

        desc = m.get("description") if isinstance(m.get("description"), str) else ""
        props = m.get("properties") if isinstance(m.get("properties"), list) else []

        # context window
        ctx = 0
        v = _get_prop(props, "context_window")
        if isinstance(v, str) and v.isdigit():
            ctx = int(v)
        elif isinstance(v, int):
            ctx = v

        supports_fc = _get_prop(props, "function_calling")
        supports_reasoning = _get_prop(props, "reasoning")

        mi: Dict[str, Any] = {
            "model": name,
            "name": name,
            "description": desc,
            "context_length": ctx,
            "max_tokens": 0,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "tags": ["cloudflare"],
            "support_url": [CF_MODELS_URL],
        }

        # 额外能力用结构化字段表达（不塞进 tags）
        if supports_fc in (True, "true", "True"):
            mi["supports_function_calling"] = True
        if supports_reasoning in (True, "true", "True"):
            mi["supports_reasoning"] = True

        items.append({"model": name, "model_info": mi})

    meta = {"name": "cloudflare", "url": CF_MODELS_URL, "note": "public models catalog (Text Generation only)"}
    return items, meta


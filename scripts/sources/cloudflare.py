from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

import requests
from bs4 import BeautifulSoup


# 公开页面（无 token）
CLOUDFLARE_MODELS_URL = "https://developers.cloudflare.com/workers-ai/models/"


def fetch(timeout_s: int = 30) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Cloudflare Workers AI：无 Secrets 的 best-effort 抓取。
    说明：文档页是给人看的，不保证稳定结构；这里主要从页面文本中提取可能的模型 ID。
    """
    headers = {
        "User-Agent": "onehub-modelinfo-pages/1.0 (+https://github.com/)",
        "Accept": "text/html,application/xhtml+xml",
    }
    r = requests.get(CLOUDFLARE_MODELS_URL, headers=headers, timeout=timeout_s)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["head", "script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)

    # Workers AI 模型常见形态：@cf/xxx/yyy 或 @cf/meta/llama-3-8b-instruct 等
    models = set(re.findall(r"@cf/[a-z0-9_\-/.]{3,120}", text, re.I))
    # 也可能出现 workers-ai model slugs（兜底）
    if not models:
        # 抓一些形如 "meta/llama-3-8b-instruct" 的片段（非常保守）
        for m in re.findall(r"\b[a-z0-9_\-]{2,30}/[a-z0-9_\-]{3,120}\b", text, re.I):
            if "/" in m and "." not in m.split("/")[0]:
                models.add(m)

    items: List[Dict[str, Any]] = []
    for mid in sorted(models):
        items.append(
            {
                "model": mid,
                "model_info": {
                    "description": "",
                    "tags": ["cloudflare"],
                },
            }
        )

    meta = {
        "name": "cloudflare",
        "url": CLOUDFLARE_MODELS_URL,
        "note": "best-effort from public docs (no key)",
    }
    return items, meta


from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

import requests
from bs4 import BeautifulSoup


GEMINI_MODELS_DOC_URL = "https://ai.google.dev/gemini-api/docs/models/gemini"


def fetch(timeout_s: int = 30) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Google Gemini：无 Secrets 的 best-effort 抓取。
    说明：官方 Models API 需要 key；这里从公开文档页提取 gemini-* 型号名。
    """
    headers = {
        "User-Agent": "onehub-modelinfo-pages/1.0 (+https://github.com/)",
        "Accept": "text/html,application/xhtml+xml",
    }
    r = requests.get(GEMINI_MODELS_DOC_URL, headers=headers, timeout=timeout_s)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["head", "script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)

    models = set(re.findall(r"\bgemini-[a-z0-9.\-]{2,60}\b", text, re.I))

    items: List[Dict[str, Any]] = []
    for mid in sorted(models):
        items.append(
            {
                "model": mid,
                "model_info": {
                    "description": "",
                    "tags": ["gemini"],
                },
            }
        )

    meta = {
        "name": "gemini",
        "url": GEMINI_MODELS_DOC_URL,
        "note": "best-effort from public docs (no key)",
    }
    return items, meta


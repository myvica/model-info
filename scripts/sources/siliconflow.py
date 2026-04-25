from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


LIST_URL = "https://www.siliconflow.com/models/serverless"
DETAIL_PREFIX = "https://www.siliconflow.com/models/"


def _clean_html_for_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["head", "script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def _extract_detail_slugs(html: str) -> List[str]:
    """
    列表页的链接格式历史上出现过：
    - href="./glm-4-7"
    - href="/models/glm-4-7"
    这里都兼容。
    """
    slugs = set()
    # 先用 soup 抓 a[href]
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        if not isinstance(href, str):
            continue
        m1 = re.match(r"^\./([a-z0-9\-]{2,80})$", href, re.I)
        if m1:
            slugs.add(m1.group(1))
            continue
        m2 = re.match(r"^/models/([a-z0-9\-]{2,80})$", href, re.I)
        if m2:
            slugs.add(m2.group(1))
            continue
    return sorted(slugs)


def _extract_model_id(text: str) -> Optional[str]:
    """
    优先提取 org/model 形式（避免把域名/字体路径误判为模型）。
    """
    # 常见噪音：带点号的域名/路径；这里直接限制 org 不含 .
    # 允许 - _ . 在 model 部分（有的模型名有 .）
    candidates = re.findall(r"\b([a-z0-9\-_]{2,40})/([a-z0-9\-_\.]{2,120})\b", text, re.I)
    for org, name in candidates:
        if "." in org:
            continue
        mid = f"{org}/{name}"
        # 进一步过滤明显不可能的
        if len(mid) < 5:
            continue
        return mid
    return None


def fetch(
    timeout_s: int = 30,
    max_models: int = 200,
    sleep_ms: int = 200,
    fail_streak_limit: int = 12,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    SiliconFlow：抓取 serverless 列表页 + 详情页（免 key）。
    注意：对站点风控敏感，做了节流与失败熔断。
    """
    headers = {
        "User-Agent": "onehub-modelinfo-pages/1.0 (+https://github.com/)",
        "Accept": "text/html,application/xhtml+xml",
    }

    r = requests.get(LIST_URL, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    slugs = _extract_detail_slugs(r.text)[:max_models]

    items: List[Dict[str, Any]] = []
    fail_streak = 0

    for slug in slugs:
        url = DETAIL_PREFIX + slug
        try:
            rr = requests.get(url, headers=headers, timeout=timeout_s)
            rr.raise_for_status()
            text = _clean_html_for_text(rr.text)
            mid = _extract_model_id(text)
            if not mid:
                raise ValueError("未能从详情页提取模型 ID")

            mi: Dict[str, Any] = {
                "description": "",
                "tags": ["siliconflow"],
            }

            # best-effort context_length（只做简单数字抓取）
            # 例：Context length 128k / 8192 等（不同页面文案可能不同）
            mnum = re.search(r"(?:context|上下文).*?(\d{3,7})", text, re.I)
            if mnum:
                try:
                    mi["context_length"] = int(mnum.group(1))
                except Exception:
                    pass

            items.append({"model": mid, "model_info": mi})
            fail_streak = 0
        except Exception:
            fail_streak += 1
            if fail_streak >= fail_streak_limit:
                break
        finally:
            time.sleep(max(0, sleep_ms) / 1000.0)

    meta = {
        "name": "siliconflow",
        "url": LIST_URL,
        "note": "serverless models (best-effort scrape, no key)",
        "max_models": max_models,
    }
    return items, meta


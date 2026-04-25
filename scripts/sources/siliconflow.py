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
    # 列表页里也会出现分类/导航：./audio ./image ./featured 等，这些不是模型详情页
    exclude = {"audio", "image", "featured"}
    # 先用 soup 抓 a[href]
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        if not isinstance(href, str):
            continue
        m1 = re.match(r"^\./([a-z0-9\-]{2,80})$", href, re.I)
        if m1:
            slug = m1.group(1).lower()
            if slug not in exclude:
                slugs.add(slug)
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


def _extract_title_and_about(html: str) -> Tuple[str, str]:
    """
    - title: 优先使用 <title>（最像“模型名”），其次 h1；用于 model_info.name
    - about: “About xxx” 段落文本，用于 description（best-effort）
    """
    soup = BeautifulSoup(html, "html.parser")
    title = ""
    # <title> 往往形如：Step-3.5-Flash - Model Info, Parameters, Benchmarks - SiliconFlow
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        # 清理固定后缀/噪音
        t = re.sub(r"\s*-\s*Model Info, Parameters, Benchmarks\s*-\s*SiliconFlow\s*\"?\s*$", "", t, flags=re.I)
        t = t.strip().strip('"').strip()
        if t:
            title = t

    # fallback：h1
    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True)

    # About 段落：优先找包含 "About" 的标题后面紧随的段落
    about = ""
    text = soup.get_text("\n", strip=True)
    m = re.search(r"\bAbout\b[^\n]*\n(.{20,800})", text, re.I)
    if m:
        about = m.group(1).strip()
    return title, about


def _parse_context_and_max_tokens(text: str) -> Tuple[int, int]:
    """
    从页面文本里 best-effort 抓：
    - Context length (如 262K)
    - Max Tokens (如 66K)
    """
    def to_int(val: str) -> int:
        val = val.strip().upper()
        if val.endswith("K") and val[:-1].replace(".", "", 1).isdigit():
            return int(float(val[:-1]) * 1000)
        if val.replace(",", "").isdigit():
            return int(val.replace(",", ""))
        return 0

    ctx = 0
    mx = 0
    m1 = re.search(r"\bContext\s*length\b[^\n]*\n([0-9.,Kk]{2,12})", text, re.I)
    if m1:
        ctx = to_int(m1.group(1))
    m2 = re.search(r"\bMax\s*Tokens\b[^\n]*\n([0-9.,Kk]{2,12})", text, re.I)
    if m2:
        mx = to_int(m2.group(1))
    # 有些卡片在底部用 “Total Context: 262K / Max output: 66K”
    if not ctx:
        m3 = re.search(r"\bTotal\s*Context\b[^\n]*\n([0-9.,Kk]{2,12})", text, re.I)
        if m3:
            ctx = to_int(m3.group(1))
    if not mx:
        m4 = re.search(r"\bMax\s*output\b[^\n]*\n([0-9.,Kk]{2,12})", text, re.I)
        if m4:
            mx = to_int(m4.group(1))
    # 兜底：只要 ctx 有值但 mx 没值，就让 mx=ctx（与旧 PHP 输出一致的“宁愿有值”策略）
    if ctx and not mx:
        mx = ctx
    return ctx, mx


def _infer_modalities(text: str, model_id: str) -> Tuple[List[str], List[str], List[str]]:
    """
    根据页面“Supported Functionality”与模型名做粗略推断：
    - 默认 text->text
    - 如果明确写了 Support image input Supported，则 input 加 image
    - 如果模型/描述包含 tts/voice/audio，则输出 audio
    """
    t = text.lower()
    input_mods = ["text"]
    output_mods = ["text"]
    extra_tags: List[str] = []

    if "support image input" in t and "supported" in t[t.find("support image input") : t.find("support image input") + 80]:
        if "image" not in input_mods:
            input_mods.append("image")

    mid = model_id.lower()
    if any(k in mid for k in ("tts", "voice", "cosyvoice", "audiollm")) or "text-to-speech" in t or " tts" in t:
        output_mods = ["audio"]

    # modality tag（与旧 PHP 风格对齐）
    in_part = "+".join(sorted(set(input_mods)))
    out_part = "+".join(sorted(set(output_mods)))
    extra_tags.append(f"modality:{in_part}->{out_part}")
    return input_mods, output_mods, extra_tags


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
    # SiliconFlow 对 UA/编码较敏感：用更接近浏览器的 header，并强制 utf-8 解码，避免出现 â 这类乱码。
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
    }

    r = requests.get(LIST_URL, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    r.encoding = "utf-8"
    slugs = _extract_detail_slugs(r.text)[:max_models]

    items: List[Dict[str, Any]] = []
    fail_streak = 0

    for slug in slugs:
        url = DETAIL_PREFIX + slug
        try:
            rr = requests.get(url, headers=headers, timeout=timeout_s)
            rr.raise_for_status()
            rr.encoding = "utf-8"
            # 只接受“模型详情页”。分类页/落地页会导致 name/description 混乱。
            soup = BeautifulSoup(rr.text, "html.parser")
            page_title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
            if not re.search(r"Model Info, Parameters, Benchmarks", page_title, re.I):
                # 非详情页，直接跳过（不计入失败熔断）
                fail_streak = 0
                continue
            text = _clean_html_for_text(rr.text)
            mid = _extract_model_id(text)
            if not mid:
                raise ValueError("未能从详情页提取模型 ID")

            title, about = _extract_title_and_about(rr.text)
            ctx, mx = _parse_context_and_max_tokens(text)
            in_mods, out_mods, modality_tags = _infer_modalities(text, mid)

            # 按需求：不输出 modality:* 这类 tags，仅保留基础分类
            tags = ["siliconflow", "serverless"]

            mi: Dict[str, Any] = {
                "model": mid,
                "name": title or mid,
                "description": about,
                "context_length": ctx,
                "max_tokens": mx,
                "input_modalities": in_mods,
                "output_modalities": out_mods,
                "tags": tags,
                "support_url": [url],
            }

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

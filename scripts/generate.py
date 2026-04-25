from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

# 允许直接运行：python scripts/generate.py
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.lib.merge import merge_items
from scripts.sources import litellm, openrouter, siliconflow


SCHEMA_VERSION = 1


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def _wrap(name: str, url: str, note: str, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": int(time.time()),
        "source": {"name": name, "url": url, "note": note},
        "data": items,
    }

def _filter_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    兜底过滤：去掉明显不合法的 model（例如包含空格的网页标题）。
    """
    out: List[Dict[str, Any]] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        model = it.get("model")
        if not isinstance(model, str):
            continue
        model = model.strip()
        if not model or any(ch.isspace() for ch in model):
            continue
        # one-hub 后端字段：Model 是 varchar(100)
        if len(model) > 100:
            continue
        it["model"] = model
        out.append(it)
    return out


def _sanitize_model_info(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    one-hub 后端字段约束（避免导入到某条时报错）：
    - name: varchar(100)
    - model: varchar(100)（已在 _filter_items 处理）
    另外做一些内容清洗，避免奇怪字符导致 UI/导入异常。
    """
    for it in items or []:
        if not isinstance(it, dict):
            continue
        mi = it.get("model_info")
        if not isinstance(mi, dict):
            continue

        # name 限长：超过 100 则截断（或干脆删掉让前端用 model 兜底）
        name = mi.get("name")
        if isinstance(name, str):
            name = name.strip().replace("\u0000", "")
            if len(name) > 100:
                name = name[:100]
            mi["name"] = name

        # description：去掉 NUL，顺便做一个保守截断（避免极端情况下渲染/传输问题）
        desc = mi.get("description")
        if isinstance(desc, str):
            desc = desc.replace("\u0000", "").strip()
            if len(desc) > 2000:
                desc = desc[:2000]
            mi["description"] = desc

        # support_url：即使 one-hub 当前导入不使用该字段，也保持为“纯 URL 字符串”
        su = mi.get("support_url")
        if isinstance(su, list):
            cleaned = []
            for u in su:
                if not isinstance(u, str):
                    continue
                u = u.strip().strip("`").strip('"').strip()
                if u:
                    cleaned.append(u)
            mi["support_url"] = cleaned

    return items


def _clean_tags(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    统一清洗 tags：
    - 删除 tokenizer:* 与 modality:*（即便未来某来源又加回来，也不会污染最终输出）
    """
    for it in items or []:
        if not isinstance(it, dict):
            continue
        mi = it.get("model_info")
        if not isinstance(mi, dict):
            continue
        tags = mi.get("tags")
        if not isinstance(tags, list):
            continue
        cleaned: List[str] = []
        seen = set()
        for t in tags:
            if not isinstance(t, str):
                continue
            if t.startswith("tokenizer:") or t.startswith("modality:"):
                continue
            if t in seen:
                continue
            seen.add(t)
            cleaned.append(t)
        mi["tags"] = cleaned
    return items


def _safe_fetch(fn, name: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    """
    单一来源失败不应导致整个构建失败（尤其是抓取类来源可能被风控）。
    返回：items, meta, err
    """
    try:
        items, meta = fn()
        return items or [], meta or {"name": name}, ""
    except Exception as e:
        return [], {"name": name}, f"{type(e).__name__}: {e}"


def _safe_fetch_any(fn, name: str):
    """
    与 _safe_fetch 类似，但允许返回任意类型的 data（例如 dict）。
    返回：data, meta, err
    """
    try:
        data, meta = fn()
        return data, meta or {"name": name}, ""
    except Exception as e:
        return None, {"name": name}, f"{type(e).__name__}: {e}"


def _litellm_enrich_existing(
    existing_items: List[Dict[str, Any]], litellm_map: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    仅对现有模型做“精确匹配补全”，不引入 LiteLLM 全量模型。
    返回 litellm_items（仅命中项），可用于：
    - 输出 litellm.model_info.json（审计补全来源）
    - 参与 merge_items(...) 以补全 onehub.model_info.json
    """
    out: List[Dict[str, Any]] = []
    for it in existing_items or []:
        model = (it or {}).get("model")
        if not isinstance(model, str) or not model:
            continue
        spec = litellm_map.get(model)
        if not isinstance(spec, dict):
            continue

        max_in = spec.get("max_input_tokens") if isinstance(spec.get("max_input_tokens"), int) else 0
        max_out = spec.get("max_output_tokens") if isinstance(spec.get("max_output_tokens"), int) else 0
        if not max_out and isinstance(spec.get("max_tokens"), int):
            max_out = int(spec["max_tokens"])

        input_mods = ["text"]
        if spec.get("supports_vision") is True:
            input_mods.append("image")
        if spec.get("supports_audio_input") is True:
            input_mods.append("audio")

        output_mods = ["text"]
        if spec.get("supports_audio_output") is True and "audio" not in output_mods:
            output_mods.append("audio")

        mi: Dict[str, Any] = {
            "model": model,
            "context_length": max_in,
            "max_tokens": max_out,
            "input_modalities": input_mods,
            "output_modalities": output_mods,
            "tags": ["litellm"],
        }
        out.append({"model": model, "model_info": mi})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist", help="输出目录（Pages 根目录）")
    args = ap.parse_args()

    out_dir = args.out
    _ensure_dir(out_dir)

    # 逐来源抓取（失败则该来源输出空 data，但仍生成文件）
    or_items, or_meta, or_err = _safe_fetch(openrouter.fetch, "openrouter")
    sf_items, sf_meta, sf_err = _safe_fetch(siliconflow.fetch, "siliconflow")
    ll_map, ll_meta, ll_err = _safe_fetch_any(litellm.fetch, "litellm")

    or_items = _filter_items(or_items)
    sf_items = _filter_items(sf_items)
    or_items = _sanitize_model_info(or_items)
    sf_items = _sanitize_model_info(sf_items)
    or_items = _clean_tags(or_items)
    sf_items = _clean_tags(sf_items)

    # LiteLLM：只对现有模型精确匹配补全（不引入新增模型）
    ll_items: List[Dict[str, Any]] = []
    if isinstance(ll_map, dict):
        ll_items = _litellm_enrich_existing(or_items + sf_items, ll_map)
        ll_items = _filter_items(ll_items)
        ll_items = _sanitize_model_info(ll_items)
        ll_items = _clean_tags(ll_items)

    # 写各来源转换后 JSON（用户要求：只保留转换后）
    _write_json(
        os.path.join(out_dir, "openrouter.model_info.json"),
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": int(time.time()),
            "source": {**or_meta, "error": or_err} if or_err else or_meta,
            "data": or_items,
        },
    )
    _write_json(
        os.path.join(out_dir, "siliconflow.model_info.json"),
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": int(time.time()),
            "source": {**sf_meta, "error": sf_err} if sf_err else sf_meta,
            "data": sf_items,
        },
    )

    # LiteLLM 补全明细（只包含命中项）
    _write_json(
        os.path.join(out_dir, "litellm.model_info.json"),
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": int(time.time()),
            "source": {**ll_meta, "error": ll_err} if ll_err else ll_meta,
            "data": ll_items,
        },
    )

    merged = merge_items(or_items, sf_items, ll_items)
    merged = _sanitize_model_info(merged)
    merged = _clean_tags(merged)
    _write_json(
        os.path.join(out_dir, "onehub.model_info.json"),
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": int(time.time()),
            "source": {
                "name": "merged",
                "note": "openrouter+siliconflow (litellm enrich by exact match)",
                "sources": [
                    {**or_meta, **({"error": or_err} if or_err else {})},
                    {**sf_meta, **({"error": sf_err} if sf_err else {})},
                    {**ll_meta, **({"error": ll_err} if ll_err else {})},
                ],
            },
            "data": merged,
        },
    )

    print("生成完成：")
    for fn in (
        "onehub.model_info.json",
        "openrouter.model_info.json",
        "siliconflow.model_info.json",
        "litellm.model_info.json",
    ):
        print(" -", os.path.join(out_dir, fn))

    # 不因为单个来源失败而失败（方便 Pages 持续更新）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

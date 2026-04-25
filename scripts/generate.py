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
from scripts.sources import openrouter, siliconflow


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
        if len(model) > 220:
            continue
        it["model"] = model
        out.append(it)
    return out


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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist", help="输出目录（Pages 根目录）")
    args = ap.parse_args()

    out_dir = args.out
    _ensure_dir(out_dir)

    # 逐来源抓取（失败则该来源输出空 data，但仍生成文件）
    or_items, or_meta, or_err = _safe_fetch(openrouter.fetch, "openrouter")
    sf_items, sf_meta, sf_err = _safe_fetch(siliconflow.fetch, "siliconflow")

    or_items = _filter_items(or_items)
    sf_items = _filter_items(sf_items)
    or_items = _clean_tags(or_items)
    sf_items = _clean_tags(sf_items)

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

    merged = merge_items(or_items, sf_items)
    merged = _clean_tags(merged)
    _write_json(
        os.path.join(out_dir, "onehub.model_info.json"),
        {
            "schema_version": SCHEMA_VERSION,
            "generated_at": int(time.time()),
            "source": {
                "name": "merged",
                "note": "openrouter+siliconflow",
                "sources": [
                    {**or_meta, **({"error": or_err} if or_err else {})},
                    {**sf_meta, **({"error": sf_err} if sf_err else {})},
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
    ):
        print(" -", os.path.join(out_dir, fn))

    # 不因为单个来源失败而失败（方便 Pages 持续更新）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

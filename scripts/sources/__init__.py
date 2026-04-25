"""
各数据源模块导出统一接口：

def fetch() -> tuple[list[dict], dict]:
  - items: one-hub 兼容条目数组：[{model, model_info}, ...]
  - source_meta: {"name": "...", "url": "...", "note": "...", ...}
"""

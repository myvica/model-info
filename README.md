# onehub-modelinfo-pages

用 GitHub Actions **每周 + 手动触发**生成 one-hub 可导入的“模型详情（model_info）”JSON，并通过 GitHub Pages 托管成一个稳定的 HTTPS 数据源（支持子域名绑定）。

## 你会得到哪些 JSON（只保留转换后）

Pages 根目录会有：

- `onehub.model_info.json`（合并总表，推荐 one-hub 直接用这个）
- `openrouter.model_info.json`
- `siliconflow.model_info.json`
- `litellm.model_info.json`（仅“命中补全明细”：只包含与现有模型同名的 LiteLLM 条目，用于补全 context/max_tokens/模态等字段）

## one-hub 怎么填

在 one-hub 面板 → **模型详情** → **批量导入**，JSON URL 填：

```
https://<你的子域名>/onehub.model_info.json
```

（也可以填任意单一来源的 `*.model_info.json`）

## 本地运行（可选）

```bash
pip install -r requirements.txt
python scripts/generate.py --out dist
ls dist
```

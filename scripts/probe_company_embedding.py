"""
公司统一 LLM 网关 embedding 探测脚本（OpenAI 兼容模式）。

用途：确定 unidt/embedding-qwen3 与 unidt/embedding-bge-m3 的维度、
时延、批量行为，为 Milvus collection 建表与模型选型提供依据。

用法（前提：gd25/.env 已配置 HUAYUAN_API_KEY / HUAYUAN_API_URL_embeddings）：
    python3 scripts/probe_company_embedding.py

不 import backend.app（独立运行，直接解析 .env，仅依赖 requests + numpy）。
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
MODELS = ["unidt/embedding-bge-m3", "unidt/embedding-qwen3"]


def load_env() -> dict:
    env: dict = {}
    env_file = ROOT / ".env"
    if not env_file.exists():
        print(f"[warn] 未找到 .env: {env_file}")
        return env
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def cosine(a: list[float], b: list[float]) -> float:
    import numpy as np

    x, y = np.asarray(a), np.asarray(b)
    return float(x @ y / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9))


def probe_model(endpoint: str, api_key: str, model: str) -> dict | None:
    # HUAYUAN_API_URL_embeddings 已是完整端点（以 /embeddings 结尾）
    url = endpoint.rstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    texts = ["该公司计划新建企业展厅", "公司与某设计院签署展示中心改造合同", "年度报告发布"]
    t0 = time.time()
    resp = requests.post(url, headers=headers, json={"model": model, "input": texts}, timeout=60)
    cost = time.time() - t0
    if resp.status_code != 200:
        print(f"  [{model}] HTTP {resp.status_code}: {resp.text[:300]}")
        return None
    data = resp.json()
    embeds = data.get("data") or []
    usage = data.get("usage") or {}
    first = embeds[0].get("embedding") or []
    dim = len(first)
    print(f"  [{model}] HTTP 200, {cost:.2f}s")
    print(f"    维度: {dim}  返回条数: {len(embeds)}  usage: {usage}")
    print(f"    样本前3位: {[round(float(x), 6) for x in first[:3]]}")
    return {"model": model, "dim": dim, "embeds": embeds, "texts": texts}


def main() -> None:
    env = load_env()
    endpoint = env.get("HUAYUAN_API_URL_embeddings") or ""
    api_key = env.get("HUAYUAN_API_KEY") or ""
    print(f"endpoint: {endpoint}")
    print(f"api_key: {'已配置' if api_key else '未配置（请先在 .env 加 HUAYUAN_API_KEY）'}")
    if not endpoint or not api_key:
        return

    results = {}
    for model in MODELS:
        r = probe_model(endpoint, api_key, model)
        if r:
            results[model] = r

    if len(results) == 2:
        # 跨模型一致性粗检：同文本的向量两两相似度（不同模型间 cosine 无意义，仅参考）
        print("\n[模型间粗对比]（同模型内 3 条文本两两余弦）")
        for model, r in results.items():
            e = r["embeds"]
            vecs = [x.get("embedding") or [] for x in e]
            if len(vecs) == 3:
                print(f"  {model}: sim(t1,t2)={cosine(vecs[0], vecs[1]):.4f} "
                      f"sim(t1,t3)={cosine(vecs[0], vecs[2]):.4f} "
                      f"sim(t2,t3)={cosine(vecs[1], vecs[2]):.4f}")


if __name__ == "__main__":
    main()

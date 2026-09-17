# 雷达采集 Worker（radar_crawl）

> **Deprecated（知识库合并 M2+）**：默认 `RADAR_KB_UNIFIED=1` 时本包 worker 启动即退出。
> 请改用仓库根目录 `python -m radar_kb discover|content|all`（写 `radar_company_news_*`，不再写 `radar_raw_document`）。

独立可发布服务，与华院 FastAPI **分开部署**。  
**默认一个启动命令拉起全部任务**（当前：列表采集 + PDF 回填）。

## 怎么用

```bash
# 仓库根目录
pip install -r requirements-radar-crawl.txt
cp radar_crawl/.env.example radar_crawl/.env   # 填 RADAR_DB_*

# 推荐：一个命令 = 全部 Worker
python -m radar_crawl

# 仅排障时才指定单个
python -m radar_crawl crawl
python -m radar_crawl pdf
```

Docker / K8s 启动命令同样是：

```bash
python -m radar_crawl
```

公司网页部署：启动参数填上面这一行即可；环境变量框填 `RADAR_DB_*`。

## 以后加新任务

编辑 `radar_crawl/registry.py`，在 `WORKERS` 列表里追加一项，例如：

```python
WorkerSpec(name="xxx", description="...", target=_run_xxx),
```

**不用改启动命令**，`python -m radar_crawl` 会自动带上新 Worker。

## 构建

```bash
docker build -f Dockerfile.radar-crawl -t unidt-exhibition-opportunity-py-crawl:latest .
```

K8s 示例：`deploy/k8s/radar-crawl.yaml`（单个 Deployment）。


## 本地启动
入口就是 radar_crawl 这个包,但要在仓库根目录跑:

### 1. 激活 conda 环境(必须,否则依赖对不上)
conda activate py311_GD25_base

### 2. 仓库根目录
cd /Users/shuxiaolong/work/github/gd25WorkHome/gd25-biz-agent-python

### 3. 只跑 PDF 回填(验证修复用)
python -m radar_crawl pdf

### 或者全开(列表采集 + PDF 回填)
python -m radar_crawl
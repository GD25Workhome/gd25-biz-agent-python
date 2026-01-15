"""
第二步：向量查询测试
测试基于向量相似度的查询功能

运行方式：
    cd cursor_test/rag/01_insertAndQuery
    python step2_query.py
"""
import sys
import os
from pathlib import Path
from urllib.parse import urlparse

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import psycopg
from sentence_transformers import SentenceTransformer
from pgvector.psycopg import register_vector

# 导入配置
try:
    from backend.app.config import settings
except ImportError:
    print("⚠️  警告: 无法导入配置，使用默认连接信息")
    settings = None

# 测试查询
TEST_QUERIES = [
    "我量了血压120/80，正常吗？",  # 应该匹配"血压达标场景"
    "今天血压有点高，135/85",      # 应该匹配"血压轻度偏高场景"
    "血压185/115，怎么办？",        # 应该匹配"血压重度偏高场景"
]


def parse_database_url(database_url: str) -> dict:
    """
    解析数据库连接URL，返回连接参数字典
    
    Args:
        database_url: 数据库连接URL，格式：postgresql+psycopg://user:password@host:port/dbname
        
    Returns:
        dict: 包含host, port, user, password, dbname的字典
    """
    # 移除驱动前缀（postgresql+psycopg:// -> postgresql://）
    url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    parsed = urlparse(url)
    
    return {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 5432,
        "user": parsed.username or "postgres",
        "password": parsed.password or "",
        "dbname": parsed.path.lstrip("/") if parsed.path else "postgres"
    }


def get_db_connection():
    """
    获取数据库连接
    
    Returns:
        psycopg.Connection: 数据库连接对象
    """
    if settings:
        # 从配置读取
        database_url = settings.DATABASE_URL
        db_config = parse_database_url(database_url)
    else:
        # 使用默认配置（从.env或环境变量读取）
        db_config = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "5433")),
            "user": os.getenv("DB_USER", "postgres"),
            "password": os.getenv("DB_PASSWORD", "sxl_pwd_123"),
            "dbname": os.getenv("DB_NAME", "gd25_biz_agent01_python")
        }
    
    # 构建连接字符串
    conn_string = (
        f"host={db_config['host']} "
        f"port={db_config['port']} "
        f"user={db_config['user']} "
        f"password={db_config['password']} "
        f"dbname={db_config['dbname']}"
    )
    
    print(f"正在连接数据库: {db_config['host']}:{db_config['port']}/{db_config['dbname']}")
    conn = psycopg.connect(conn_string)
    
    # 注册vector类型
    register_vector(conn)
    
    return conn


def text_to_embedding(text: str, model: SentenceTransformer) -> list:
    """
    将文本转换为768维向量
    
    Args:
        text: 输入文本
        model: SentenceTransformer模型实例
        
    Returns:
        list: 768维向量列表
    """
    embedding = model.encode(text, normalize_embeddings=True)
    return embedding.tolist()


def search_similar_entries(conn, query_embedding: list, top_k: int = 3):
    """
    基于向量相似度检索相关知识条目
    
    Args:
        conn: 数据库连接
        query_embedding: 查询向量（768维）
        top_k: 返回Top-K个最相似的结果
        
    Returns:
        list: 检索结果列表，每个元素包含：
            - scene_name: 场景名称
            - scene_conditions: 场景条件
            - patient_example: 患者示例
            - reply_template: 回复模板
            - similarity: 相似度分数（余弦相似度，范围0-1）
    """
    with conn.cursor() as cur:
        # 使用余弦相似度查询（1 - 余弦距离 = 余弦相似度）
        # pgvector的 <-> 操作符计算余弦距离，1 - 距离 = 相似度
        cur.execute("""
            SELECT 
                scene_name,
                scene_conditions,
                patient_example,
                reply_template,
                1 - (embedding <-> %s::vector) as similarity
            FROM test_knowledge_base
            ORDER BY embedding <-> %s::vector
            LIMIT %s
        """, (query_embedding, query_embedding, top_k))
        
        results = []
        for row in cur.fetchall():
            results.append({
                "scene_name": row[0],
                "scene_conditions": row[1],
                "patient_example": row[2],
                "reply_template": row[3],
                "similarity": float(row[4])
            })
        
        return results


def search_with_threshold(
    conn, 
    query_embedding: list, 
    top_k: int = 3,
    similarity_threshold: float = 0.7
):
    """
    带相似度阈值的检索
    
    Args:
        conn: 数据库连接
        query_embedding: 查询向量（768维）
        top_k: 返回Top-K个最相似的结果
        similarity_threshold: 相似度阈值，低于此值的结果将被过滤
        
    Returns:
        list: 过滤后的检索结果
    """
    results = search_similar_entries(conn, query_embedding, top_k)
    
    # 过滤低相似度结果
    filtered_results = [
        r for r in results 
        if r['similarity'] >= similarity_threshold
    ]
    
    return filtered_results


def print_search_results(query: str, results: list, use_threshold: bool = False):
    """
    打印检索结果
    
    Args:
        query: 查询文本
        results: 检索结果列表
        use_threshold: 是否使用了阈值过滤
    """
    print(f"\n查询: \"{query}\"")
    
    if not results:
        print("  ⚠️  未找到相关结果")
        if use_threshold:
            print("  （可能是相似度阈值过高，尝试降低阈值或查看所有结果）")
        return
    
    print(f"  检索结果（Top-{len(results)}）：")
    for i, result in enumerate(results, 1):
        similarity = result['similarity']
        similarity_bar = "█" * int(similarity * 20)  # 可视化相似度
        
        print(f"\n    [{i}] {result['scene_name']} (相似度: {similarity:.3f}) {similarity_bar}")
        print(f"        场景条件: {result['scene_conditions']}")
        print(f"        患者示例: {result['patient_example']}")
        print(f"        回复模板: {result['reply_template']}")


def main():
    """主函数"""
    print("=" * 60)
    print("第二步：向量查询测试")
    print("=" * 60)
    print()
    
    try:
        # 1. 连接数据库
        conn = get_db_connection()
        print("✓ 数据库连接成功")
        print()
        
        # 2. 检查表中是否有数据
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM test_knowledge_base")
            count = cur.fetchone()[0]
            
            if count == 0:
                print("⚠️  警告: 测试表中没有数据")
                print("  请先运行 step1_insert.py 插入测试数据")
                conn.close()
                sys.exit(1)
            
            print(f"✓ 测试表中有 {count} 条记录")
            print()
        
        # 3. 加载embedding模型
        print("正在加载Embedding模型（moka-ai/m3e-base）...")
        
        # 检查模型是否已下载到本地缓存
        cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
        model_dir = cache_dir / "models--moka-ai--m3e-base"
        model_exists = model_dir.exists() and (model_dir / "snapshots").exists()
        
        if model_exists:
            print("  ✓ 检测到本地模型缓存，将使用本地模型（无需下载，离线模式）")
            # 使用 local_files_only=True 避免网络请求
            model = SentenceTransformer('moka-ai/m3e-base', local_files_only=True)
        else:
            print("  ⚠️  未检测到本地模型，将自动下载（首次运行，可能需要一些时间）")
            # 需要从网络下载，不使用 local_files_only
            model = SentenceTransformer('moka-ai/m3e-base')
        print("✓ Embedding模型加载成功")
        print()
        
        # 4. 遍历测试查询
        print("=" * 60)
        print("开始向量查询测试...")
        print("=" * 60)
        
        for i, query in enumerate(TEST_QUERIES, 1):
            print(f"\n[测试 {i}/{len(TEST_QUERIES)}]")
            
            # 对查询进行向量化
            query_embedding = text_to_embedding(query, model)
            
            # 执行向量相似度查询
            results = search_similar_entries(conn, query_embedding, top_k=3)
            
            # 打印结果
            print_search_results(query, results, use_threshold=False)
            
            # 测试带阈值的查询（阈值0.7）
            print(f"\n  [带阈值过滤（相似度>=0.7）]")
            threshold_results = search_with_threshold(
                conn, 
                query_embedding, 
                top_k=3,
                similarity_threshold=0.7
            )
            print_search_results(query, threshold_results, use_threshold=True)
        
        print()
        print("=" * 60)
        print("✓ 向量查询测试完成")
        print("=" * 60)
        
        # 关闭连接
        conn.close()
        
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
第一步：向量存储测试
测试将文本数据向量化并存储到PostgreSQL向量库

运行方式：
    cd cursor_test/rag/01_insertAndQuery
    python step1_insert.py
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

# 测试数据
TEST_DATA = [
    {
        "scene_name": "血压达标场景",
        "scene_conditions": "90<=收缩压<=目标值 且 舒张压<=目标值",
        "patient_example": "我今天量了血压，120/80",
        "reply_template": "赞！血压已达标，继续加油保持！"
    },
    {
        "scene_name": "血压轻度偏高场景",
        "scene_conditions": "收缩压、舒张压任一值超过了对应设定目标值，但两者超过了均不到10mmHg",
        "patient_example": "我今天的血压是135/85，有点高",
        "reply_template": "我看到您本次测量的血压稍高，建议遵医嘱，规律用药，保持降压生活方式。"
    },
    {
        "scene_name": "血压重度偏高场景",
        "scene_conditions": "收缩压>=180 or 舒张压>=110",
        "patient_example": "我量了血压，高压185，低压115",
        "reply_template": "您本次测量的血压过高，建议您尽快到医院就诊，由医生判断是否需要调整治疗方案。"
    }
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


def create_test_table(conn):
    """
    创建测试表
    
    Args:
        conn: 数据库连接
    """
    with conn.cursor() as cur:
        # 创建表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS test_knowledge_base (
                id SERIAL PRIMARY KEY,
                scene_name VARCHAR(200) NOT NULL,
                scene_conditions TEXT,
                patient_example TEXT,
                reply_template TEXT,
                embedding vector(768),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        
        # 创建向量索引（HNSW，用于快速相似度搜索）
        cur.execute("""
            CREATE INDEX IF NOT EXISTS test_knowledge_base_embedding_idx 
            ON test_knowledge_base 
            USING hnsw (embedding vector_cosine_ops)
        """)
        
        conn.commit()
        print("✓ 测试表创建成功")


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


def insert_knowledge_entry(conn, entry: dict, model: SentenceTransformer):
    """
    插入知识库条目
    
    Args:
        conn: 数据库连接
        entry: 知识条目字典
        model: SentenceTransformer模型实例
    """
    # 构建向量化文本（用于检索）
    # 组合多个字段：场景名称 + 场景条件 + 患者示例
    text_for_embedding = (
        f"{entry['scene_name']} "
        f"{entry['scene_conditions']} "
        f"{entry['patient_example']}"
    )
    
    # 生成向量
    embedding_vector = text_to_embedding(text_for_embedding, model)
    
    # 插入数据
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO test_knowledge_base 
            (scene_name, scene_conditions, patient_example, reply_template, embedding)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            entry['scene_name'],
            entry['scene_conditions'],
            entry['patient_example'],
            entry['reply_template'],
            embedding_vector  # psycopg会自动转换为vector类型
        ))
    
    conn.commit()


def verify_insert(conn):
    """
    验证插入结果
    
    Args:
        conn: 数据库连接
    """
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM test_knowledge_base")
        count = cur.fetchone()[0]
        
        cur.execute("""
            SELECT scene_name, 
                   LENGTH(embedding::text) as embedding_length
            FROM test_knowledge_base
            LIMIT 3
        """)
        rows = cur.fetchall()
        
        print(f"\n✓ 成功插入 {count} 条记录")
        print("\n验证数据：")
        for row in rows:
            print(f"  - {row[0]} (向量长度: {row[1]} 字符)")


def main():
    """主函数"""
    print("=" * 60)
    print("第一步：向量存储测试")
    print("=" * 60)
    print()
    
    try:
        # 1. 连接数据库
        conn = get_db_connection()
        print("✓ 数据库连接成功")
        print()
        
        # 2. 创建表（如果不存在）
        print("正在创建测试表...")
        create_test_table(conn)
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
        print(f"  模型维度: {model.get_sentence_embedding_dimension()}")
        print()
        
        # 4. 清空测试表（可选，用于重复测试）
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE test_knowledge_base RESTART IDENTITY")
            conn.commit()
        print("✓ 已清空测试表（准备插入新数据）")
        print()
        
        # 5. 遍历测试数据，向量化并插入
        print("正在插入测试数据...")
        for i, entry in enumerate(TEST_DATA, 1):
            print(f"  [{i}/{len(TEST_DATA)}] 插入：{entry['scene_name']}")
            insert_knowledge_entry(conn, entry, model)
        
        print()
        
        # 6. 验证插入结果
        verify_insert(conn)
        
        print()
        print("=" * 60)
        print("✓ 向量存储测试完成")
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

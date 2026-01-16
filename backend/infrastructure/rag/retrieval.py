"""
RAG向量库检索模块
实现向量库检索功能，支持多表检索和结果合并
"""
import logging
from typing import List, Dict, Optional

import numpy as np
import psycopg

from backend.infrastructure.database.vector_connection import get_vector_db_connection
from backend.infrastructure.rag.data_import import EmbeddingModelCache

logger = logging.getLogger(__name__)

# 表名列表（需要检索的所有表）
TABLE_NAMES = [
    "qa_examples",
    "record_examples",
    "query_examples",
    "greeting_examples",
]

# 表前缀
TABLE_PREFIX = "gd2502_"


def search_in_table(
    conn: psycopg.Connection,
    table_name: str,
    query_embedding: np.ndarray,
    top_k: int = 5,
    similarity_threshold: float = 0.7
) -> List[Dict]:
    """
    在单个表中执行向量检索
    
    Args:
        conn: 数据库连接
        table_name: 表名（不含前缀）
        query_embedding: 查询向量（numpy数组）
        top_k: 返回数量
        similarity_threshold: 相似度阈值
    
    Returns:
        List[Dict]: 检索结果列表
    """
    full_table_name = f"{TABLE_PREFIX}{table_name}"
    
    # 将numpy数组转换为列表
    embedding_list = query_embedding.tolist()
    
    # SQL查询：使用余弦相似度
    sql = f"""
        SELECT 
            id,
            user_input,
            agent_response,
            tags,
            quality_grade,
            1 - (embedding <=> %s::vector) AS similarity_score,
            %s AS source
        FROM {full_table_name}
        WHERE 1 - (embedding <=> %s::vector) >= %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (
                embedding_list,
                table_name,
                embedding_list,
                similarity_threshold,
                embedding_list,
                top_k
            ))
            
            results = []
            for row in cur.fetchall():
                results.append({
                    'id': row[0],
                    'user_input': row[1],
                    'agent_response': row[2],
                    'tags': row[3] if row[3] else [],
                    'quality_grade': row[4],
                    'similarity': float(row[5]),
                    'source': row[6],
                    'metadata': {
                        'tags': row[3] if row[3] else [],
                        'quality_grade': row[4]
                    }
                })
            
            return results
    
    except Exception as e:
        logger.error(f"表 {table_name} 检索失败: {e}")
        return []


def multi_table_search(
    query_embedding: np.ndarray,
    table_names: List[str] = None,
    top_k_per_table: int = 5,
    similarity_threshold: float = 0.7,
    conn: Optional[psycopg.Connection] = None
) -> List[Dict]:
    """
    多表检索，合并结果
    
    Args:
        query_embedding: 查询向量
        table_names: 表名列表（如果为None，检索所有表）
        top_k_per_table: 每个表检索的数量
        similarity_threshold: 相似度阈值
        conn: 数据库连接（如果为None，会创建新连接）
    
    Returns:
        List[Dict]: 合并后的检索结果，按相似度排序
    """
    if table_names is None:
        table_names = TABLE_NAMES
    
    # 如果没有提供连接，创建新连接
    should_close = False
    if conn is None:
        conn = get_vector_db_connection()
        should_close = True
    
    try:
        all_results = []
        
        # 对每个表执行检索
        for table_name in table_names:
            results = search_in_table(
                conn=conn,
                table_name=table_name,
                query_embedding=query_embedding,
                top_k=top_k_per_table,
                similarity_threshold=similarity_threshold
            )
            all_results.extend(results)
        
        # 按相似度排序（降序）
        all_results.sort(key=lambda x: x['similarity'], reverse=True)
        
        return all_results
    
    finally:
        if should_close:
            conn.close()


def search_with_fallback(
    query_embedding: np.ndarray,
    table_names: List[str] = None,
    min_results: int = 5,
    top_k_per_table: int = 5,
    conn: Optional[psycopg.Connection] = None
) -> List[Dict]:
    """
    带降级的检索（如果结果不足，降低阈值重试）
    
    Args:
        query_embedding: 查询向量
        table_names: 表名列表
        min_results: 最小结果数量
        top_k_per_table: 每个表检索的数量
        conn: 数据库连接
    
    Returns:
        List[Dict]: 检索结果列表
    """
    thresholds = [0.7, 0.6, 0.5]  # 降级阈值列表
    
    for threshold in thresholds:
        results = multi_table_search(
            query_embedding=query_embedding,
            table_names=table_names,
            top_k_per_table=top_k_per_table,
            similarity_threshold=threshold,
            conn=conn
        )
        
        if len(results) >= min_results:
            logger.info(f"检索成功：阈值 {threshold}，结果数量 {len(results)}")
            return results
    
    # 如果所有阈值都不满足，返回已有结果（即使数量不足）
    logger.warning(f"检索结果不足：仅找到 {len(results)} 个结果（期望至少 {min_results} 个）")
    return results


def vector_db_search(
    query_text: str,
    keywords: List[str] = None,
    top_k: int = 15,
    similarity_threshold: float = 0.7,
    table_names: List[str] = None,
    min_results: int = 5
) -> List[Dict]:
    """
    向量库检索主函数
    
    Args:
        query_text: 查询文本（来自节点1）
        keywords: 关键词列表（可选，用于增强检索）
        top_k: 返回数量（默认15）
        similarity_threshold: 相似度阈值（默认0.7）
        table_names: 要检索的表名列表（如果为None，检索所有表）
        min_results: 最小结果数量（用于降级策略）
    
    Returns:
        List[Dict]: 检索结果列表，每个元素包含：
            - user_input: 用户输入
            - agent_response: Agent回复
            - tags: 标签列表
            - quality_grade: 质量等级
            - similarity: 相似度分数
            - source: 来源表名
            - metadata: 元数据
    """
    if not query_text:
        logger.warning("查询文本为空，返回空结果")
        return []
    
    # 关键词增强（可选）
    if keywords:
        enhanced_query = f"{query_text} {' '.join(keywords)}"
    else:
        enhanced_query = query_text
    
    # 向量化
    embedding_cache = EmbeddingModelCache()
    query_embedding = np.array(embedding_cache.text_to_embedding(enhanced_query))
    
    # 执行检索（带降级策略）
    results = search_with_fallback(
        query_embedding=query_embedding,
        table_names=table_names,
        min_results=min_results,
        top_k_per_table=5,  # 每个表检索5个，总共最多20个，然后取Top-K
        conn=None  # 自动创建连接
    )
    
    # 取前Top-K个结果
    if len(results) > top_k:
        results = results[:top_k]
    
    logger.info(f"检索完成：查询文本='{query_text[:50]}...'，返回 {len(results)} 个结果")
    
    return results

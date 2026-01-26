"""
RAG Agent节点创建器
实现向量检索功能，从案例库中召回相似案例
"""
import logging
from typing import Callable, List, Dict, Optional

import numpy as np
import psycopg
from pgvector.psycopg import register_vector

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.models.definition import (
    FlowDefinition, NodeDefinition, RagAgentNodeConfig, ModelConfig, EmbeddingNodeConfig
)
from backend.domain.embeddings.factory import EmbeddingFactory
from backend.domain.embeddings.executor import EmbeddingExecutor
from backend.infrastructure.database.vector_connection import get_vector_db_connection
from backend.infrastructure.database.base import TABLE_PREFIX
from backend.infrastructure.llm.providers.manager import ProviderManager

logger = logging.getLogger(__name__)


class RagAgentNodeCreator(NodeCreator):
    """RAG Agent节点创建器"""
    
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建 RAG Agent 节点函数
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: 节点函数（异步函数，接收 FlowState，返回 FlowState）
        """
        # 解析节点配置
        config_dict = node_def.config
        model_dict = config_dict["model"].copy()
        
        # 如果缺少 name 字段，尝试从 provider 配置中获取默认值
        if "name" not in model_dict or not model_dict["name"]:
            provider_name = model_dict.get("provider")
            if provider_name:
                # 确保 ProviderManager 已加载
                if not ProviderManager.is_loaded():
                    ProviderManager.load_providers()
                
                provider_config = ProviderManager.get_provider(provider_name)
                if provider_config and provider_config.default_model:
                    model_dict["name"] = provider_config.default_model
                    logger.info(
                        f"[节点 {node_def.name}] 使用 provider '{provider_name}' 的默认模型: "
                        f"{provider_config.default_model}"
                    )
        
        # 创建 ModelConfig
        model_config = ModelConfig(**model_dict)
        
        # 创建 RagAgentNodeConfig（使用默认值填充可选配置）
        rag_config = RagAgentNodeConfig(
            model=model_config,
            top_k=config_dict.get("top_k", 5),
            similarity_threshold=config_dict.get("similarity_threshold", 0.5),
            output_field=config_dict.get("output_field", "retrieved_examples")
        )
        
        # 创建 Embedding 执行器
        # 注意：需要将 RagAgentNodeConfig 转换为 EmbeddingNodeConfig 格式
        embedding_config = EmbeddingNodeConfig(
            model=rag_config.model,
            input={"filed": "query_text"},  # 临时配置，实际不使用
            output={"filed": rag_config.output_field}  # 临时配置，实际不使用
        )
        embedding_executor = EmbeddingFactory.create_embedding_executor(
            config=embedding_config
        )
        
        # 提取配置
        top_k = rag_config.top_k
        similarity_threshold = rag_config.similarity_threshold
        output_field = rag_config.output_field
        node_name = node_def.name
        
        # 创建节点函数
        async def rag_node_action(state: FlowState) -> FlowState:
            """RAG Agent 节点函数"""
            # 1. 从 edges_var 读取输入数据并格式化
            edges_var = state.get("edges_var", {})
            query_text = self._extract_and_format_query_text(edges_var, node_name)
            
            if not query_text or not query_text.strip():
                error_msg = (
                    f"[节点 {node_name}] 查询文本为空，"
                    f"需要 scene_summary 或 optimization_question 至少一个字段，"
                    f"当前 edges_var: {edges_var}"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            logger.info(
                # f"[节点 {node_name}] 开始检索，查询文本: {query_text[:50]}..."
                f"[节点 {node_name}] 开始检索，查询文本: {query_text}"
            )
            
            # 2. 调用 embedding 模型生成向量
            try:
                embeddings = await embedding_executor.ainvoke([query_text])
                if not embeddings or len(embeddings) == 0:
                    raise RuntimeError("Embedding 模型返回空结果")
                query_embedding = np.array(embeddings[0])
                logger.debug(
                    f"[节点 {node_name}] 成功生成向量，维度: {len(query_embedding)}"
                )
            except Exception as e:
                error_msg = f"[节点 {node_name}] 调用 embedding 模型失败: {e}"
                logger.error(error_msg, exc_info=True)
                raise RuntimeError(error_msg) from e
            
            # 3. 执行向量检索
            try:
                retrieved_results = self._search_similar_cases(
                    query_embedding=query_embedding,
                    top_k=top_k,
                    similarity_threshold=similarity_threshold
                )
                logger.info(
                    f"[节点 {node_name}] 检索完成，找到 {len(retrieved_results)} 个相似案例"
                )
            except Exception as e:
                error_msg = f"[节点 {node_name}] 向量检索失败: {e}"
                logger.error(error_msg, exc_info=True)
                raise RuntimeError(error_msg) from e
            
            # 4. 格式化检索结果
            formatted_examples = self._format_retrieved_examples(retrieved_results)
            
            # 5. 更新状态
            new_state = state.copy()
            
            # 关键：每次创建新 state 时，edges_var 使用新字典，不继承原始值
            # 确保上游节点的数据不会污染下游节点的条件判断
            new_state["edges_var"] = {}
            
            # 将结果保存到 prompt_vars，以便下游 agent 节点可以在 prompt 模板中使用
            # 初始化 prompt_vars（如果不存在）
            if "prompt_vars" not in new_state:
                new_state["prompt_vars"] = {}
            # elif not isinstance(new_state["prompt_vars"], dict):
            #     # 如果 prompt_vars 存在但不是字典，重新初始化
            #     new_state["prompt_vars"] = {}
            
            new_state["prompt_vars"][output_field] = formatted_examples
            
            logger.debug(
                f"[节点 {node_name}] 将检索结果保存到 prompt_vars['{output_field}']，"
                f"结果长度: {len(formatted_examples)} 字符"
            )
            
            return new_state
        
        return rag_node_action
    
    def _extract_and_format_query_text(self, edges_var: dict, node_name: str) -> str:
        """
        从 edges_var 中提取并格式化查询文本
        
        提取 scene_summary 和 optimization_question 两个字段，
        按照 before_embedding_func 的格式拼接（但不包含 ai_response）
        
        Args:
            edges_var: 边变量字典
            node_name: 节点名称（用于日志）
        
        Returns:
            str: 格式化后的查询文本
        """
        # 提取两个字段
        scene_summary = edges_var.get("scene_summary")
        optimization_question = edges_var.get("optimization_question")
        
        # 去除首尾空白
        scene_summary = (scene_summary or "").strip() if scene_summary else ""
        optimization_question = (optimization_question or "").strip() if optimization_question else ""
        
        # 如果两个字段都为空，返回空字符串
        if not scene_summary and not optimization_question:
            logger.warning(
                f"[节点 {node_name}] scene_summary 和 optimization_question 都为空，"
                f"当前 edges_var: {edges_var}"
            )
            return ""
        
        # 按照格式拼接（参考 before_embedding_func._format_embedding_str，但不包含 ai_response）
        parts = []
        if scene_summary:
            parts.append(scene_summary)
        if optimization_question:
            parts.append(f"问题：{optimization_question}")
        
        query_text = "\n".join(parts)
        logger.debug(
            f"[节点 {node_name}] 提取并格式化查询文本，"
            f"scene_summary: {scene_summary[:50] if scene_summary else 'None'}..., "
            f"optimization_question: {optimization_question[:50] if optimization_question else 'None'}..."
        )
        
        return query_text
    
    def _search_similar_cases(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        similarity_threshold: float = 0.7
    ) -> List[Dict]:
        """
        在 embedding_record 表中检索相似案例
        
        Args:
            query_embedding: 查询向量（numpy数组）
            top_k: 返回数量
            similarity_threshold: 相似度阈值
        
        Returns:
            List[Dict]: 检索结果列表，每个元素包含：
                - scene_summary: 场景摘要
                - optimization_question: 优化后的问题
                - ai_response: AI回复
                - similarity: 相似度分数
        """
        table_name = f"{TABLE_PREFIX}embedding_records"
        
        # 将numpy数组转换为列表
        embedding_list = query_embedding.tolist()
        
        # 降级策略：如果结果不足，逐步降低阈值
        thresholds = [similarity_threshold, similarity_threshold - 0.1, similarity_threshold - 0.2]
        thresholds = [max(0.3, t) for t in thresholds]  # 确保阈值不低于0.3
        
        conn = None
        try:
            conn = get_vector_db_connection()
            
            for threshold in thresholds:
                # SQL查询：使用余弦相似度
                sql = f"""
                    SELECT 
                        id,
                        scene_summary,
                        optimization_question,
                        ai_response,
                        1 - (embedding_value <=> %s::vector) AS similarity_score
                    FROM {table_name}
                    WHERE embedding_value IS NOT NULL
                      AND 1 - (embedding_value <=> %s::vector) >= %s

                    ORDER BY embedding_value <=> %s::vector
                    LIMIT %s
                """
                                    #   AND is_published = true

                with conn.cursor() as cur:
                    cur.execute(sql, (
                        embedding_list,
                        embedding_list,
                        threshold,
                        embedding_list,
                        top_k
                    ))
                    
                    results = []
                    for row in cur.fetchall():
                        results.append({
                            'id': row[0],
                            'scene_summary': row[1] or '',
                            'optimization_question': row[2] or '',
                            'ai_response': row[3] or '',
                            'similarity': float(row[4])
                        })
                    
                    # 如果结果数量足够，返回结果
                    if len(results) >= min(3, top_k):  # 至少返回3个或top_k个（取较小值）
                        logger.debug(
                            f"检索成功：阈值 {threshold}，结果数量 {len(results)}"
                        )
                        return results
            
            # 如果所有阈值都不满足，返回已有结果（即使数量不足）
            logger.warning(
                f"检索结果不足：仅找到 {len(results)} 个结果（期望至少 {min(3, top_k)} 个）"
            )
            return results
            
        except Exception as e:
            logger.error(f"向量检索失败: {e}", exc_info=True)
            raise
        finally:
            if conn:
                conn.close()
    
    def _format_retrieved_examples(self, results: List[Dict]) -> str:
        """
        将检索结果格式化为 fewshot 示例文本
        
        Args:
            results: 检索结果列表
        
        Returns:
            str: 格式化的 fewshot 文本
        """
        if not results:
            return ""
        
        formatted_lines = ["## 相似案例示例", ""]
        
        for idx, result in enumerate(results, 1):
            similarity = result.get('similarity', 0.0)
            scene_summary = result.get('scene_summary', '')
            optimization_question = result.get('optimization_question', '')
            ai_response = result.get('ai_response', '')
            
            formatted_lines.append(f"### 案例 {idx}（相似度：{similarity:.2f}）")
            if scene_summary:
                formatted_lines.append(f"**用户场景**：{scene_summary}")
            if optimization_question:
                formatted_lines.append(f"**用户问题**：{optimization_question}")
            if ai_response:
                formatted_lines.append(f"**AI回复**：{ai_response}")
            formatted_lines.append("")  # 空行分隔
        
        return "\n".join(formatted_lines)

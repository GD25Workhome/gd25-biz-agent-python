"""
RAG检索节点实现
负责从向量库检索相关示例，格式化后传递给下游节点
"""
import logging
from typing import List, Dict
from langchain_core.messages import HumanMessage

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base_function import BaseFunctionNode
from backend.infrastructure.rag.retrieval import (
    vector_db_search,
    search_popular_science_articles,
    TABLE_NAMES
)
from backend.infrastructure.rag.formatter import format_retrieved_examples

logger = logging.getLogger(__name__)


class RetrievalNodeV2(BaseFunctionNode):
    """RAG检索节点"""
    
    @classmethod
    def get_key(cls) -> str:
        """返回节点的唯一标识key"""
        return "retrieval_node_v2"
    
    def _retrieve_examples(
        self,
        query_text: str,
        keywords: List[str]
    ) -> List[Dict]:
        """
        查询回复案例（使用query_text和keywords）
        
        Args:
            query_text: 优化后的问题文本
            keywords: 核心关键词列表
        
        Returns:
            List[Dict]: 检索到的回复案例列表
        """
        if not query_text:
            logger.warning("查询文本为空，无法检索回复案例")
            return []
        
        logger.info(f"开始检索回复案例：query_text='{query_text[:50]}...', keywords={keywords}")
        
        retrieved_examples = vector_db_search(
            query_text=query_text,
            keywords=keywords,
            top_k=15,
            similarity_threshold=0.7,
            table_names=TABLE_NAMES,  # 指定表名列表
            min_results=5
        )
        
        logger.info(f"回复案例检索完成：检索到 {len(retrieved_examples)} 个示例")
        return retrieved_examples
    
    def _retrieve_articles(self, disease: str) -> List[Dict]:
        """
        查询科普文章（使用disease）
        
        Args:
            disease: 疾病名称
        
        Returns:
            List[Dict]: 检索到的科普文章列表
        """
        if not disease:
            logger.info("疾病名为空，跳过科普文章检索")
            return []
        
        logger.info(f"开始检索科普文章：disease='{disease}'")
        
        articles = search_popular_science_articles(
            disease=disease,
            top_k=5,
            similarity_threshold=0.7,
            min_results=3
        )
        
        logger.info(f"科普文章检索完成：检索到 {len(articles)} 篇文章")
        return articles
    
    async def execute(self, state: FlowState) -> FlowState:
        """
        RAG检索节点执行逻辑（异步）
        
        功能：
        1. 从state中读取上游节点的输出（query_text、keywords）
        2. 执行向量库检索
        3. 格式化检索结果
        4. 将结果写入state，传递给下游节点
        
        Args:
            state: 流程状态对象（FlowState）
        
        Returns:
            FlowState: 更新后的状态对象
        """
        try:
            # 1. 获取上游节点的输出
            prompt_vars = state.get("edges_var", {})
            query_text = prompt_vars.get("query_text", "")
            keywords = prompt_vars.get("keywords", [])
            disease = prompt_vars.get("disease", "")
            
            # 2. 回退到原始输入（如果query_text为空）
            if not query_text:
                current_message = state.get("current_message")
                if current_message and isinstance(current_message, HumanMessage):
                    query_text = current_message.content
                    logger.info(f"query_text为空，使用原始输入: {query_text[:50]}...")
            
            # 3. 查询回复案例（使用query_text和keywords）
            retrieved_examples = self._retrieve_examples(
                query_text=query_text,
                keywords=keywords
            )
            
            # 4. 查询科普文章（使用disease）
            articles = self._retrieve_articles(disease=disease)
            
            # 5. 格式化回复案例结果
            formatted_examples = format_retrieved_examples(retrieved_examples)
            
            # 6. 更新状态
            new_state = state.copy()
            if "prompt_vars" not in new_state:
                new_state["prompt_vars"] = {}
            
            # 将回复案例结果放在retrieved_examples中
            new_state["prompt_vars"]["retrieved_examples"] = formatted_examples
            
            # 可以将科普文章结果也放入state中
            new_state["prompt_vars"]["retrieved_articles"] = articles
            
            logger.info(f"检索完成：回复案例 {len(retrieved_examples)} 个，科普文章 {len(articles)} 篇")
            
            return new_state
            
        except Exception as e:
            logger.error(f"RAG检索节点执行失败: {e}", exc_info=True)
            # 降级：返回空结果，不阻塞流程
            new_state = state.copy()
            if "prompt_vars" not in new_state:
                new_state["prompt_vars"] = {}
            new_state["prompt_vars"]["retrieved_examples"] = "（暂无相关示例）"
            return new_state

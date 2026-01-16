"""
RAG检索结果格式化模块
将检索结果格式化为节点3可用的格式
"""
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def format_retrieved_examples(results: List[Dict]) -> str:
    """
    格式化检索结果，生成节点3可用的示例文本（Markdown格式）
    
    Args:
        results: 检索结果列表（来自vector_db_search），每个元素包含：
            - user_input: 用户输入
            - agent_response: Agent回复
            - tags: 标签列表
            - quality_grade: 质量等级
            - similarity: 相似度分数
            - source: 来源表名
            - metadata: 元数据
    
    Returns:
        str: 格式化的Markdown示例文本（用于注入提示词），多个例子之间用换行分隔
    """
    if not results:
        return "（暂无相关示例）"
    
    all_content_lines = []
    
    for idx, result in enumerate(results, 1):
        # 提取字段
        user_input = result.get('user_input', '')
        agent_response = result.get('agent_response', '')
        tags = result.get('tags', [])
        
        # 格式化标签：如果是列表则用逗号连接，否则直接使用
        if isinstance(tags, list):
            tags_str = ', '.join(str(tag) for tag in tags) if tags else '无'
        else:
            tags_str = str(tags) if tags else '无'
        
        # 构建Markdown格式的示例文本
        # 格式：
        # - 例子1
        #   - 标签 : ....
        #   - 用户提问 : ......
        #   - 回复例子（思路） : ......
        content_lines = [
            f"- 例子{idx}",
            f"  - 标签 : {tags_str}",
            f"  - 用户提问 : {user_input}",
            f"  - 回复例子（思路） : {agent_response}"
        ]
        all_content_lines.extend(content_lines)
        # 每个例子之间添加空行分隔（最后一个例子不加）
        if idx < len(results):
            all_content_lines.append("")
    
    result_text = "\n".join(all_content_lines)
    logger.debug(f"格式化完成：{len(results)} 个示例")
    return result_text


def format_examples_for_prompt(examples: List[Dict], max_examples: int = 10) -> str:
    """
    将格式化的示例列表转换为提示词文本
    
    Args:
        examples: 格式化后的示例列表
        max_examples: 最大示例数量（用于限制提示词长度）
    
    Returns:
        str: 格式化的示例文本（用于注入提示词）
    """
    if not examples:
        return "（暂无相关示例）"
    
    # 限制示例数量
    if len(examples) > max_examples:
        examples = examples[:max_examples]
    
    # 构建文本
    lines = []
    for i, example in enumerate(examples, 1):
        content = example.get('content', '')
        similarity = example.get('similarity', 0.0)
        source = example.get('source', 'unknown')
        
        lines.append(f"示例 {i}（相似度: {similarity:.2f}, 来源: {source}）：")
        lines.append(content)
        lines.append("")  # 空行分隔
    
    return "\n".join(lines)

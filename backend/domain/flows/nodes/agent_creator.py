"""
Agent节点创建器
"""
import logging
import json
from typing import Callable

from langchain_core.messages import AIMessage

from backend.domain.state import FlowState
from backend.domain.flows.nodes.base import NodeCreator
from backend.domain.flows.models.definition import FlowDefinition, NodeDefinition, AgentNodeConfig, ModelConfig
from backend.domain.agents.factory import AgentFactory
from backend.infrastructure.prompts.sys_prompt_builder import build_system_message

logger = logging.getLogger(__name__)


class AgentNodeCreator(NodeCreator):
    """Agent节点创建器"""
    
    def create(self, node_def: NodeDefinition, flow_def: FlowDefinition) -> Callable:
        """
        创建Agent节点函数
        
        Args:
            node_def: 节点定义
            flow_def: 流程定义
            
        Returns:
            Callable: Agent节点函数
        """
        # 解析节点配置
        config_dict = node_def.config
        model_config = ModelConfig(**config_dict["model"])
        agent_config = AgentNodeConfig(
            prompt=config_dict["prompt"],
            model=model_config,
            tools=config_dict.get("tools")
        )
        
        # 创建Agent
        agent_executor = AgentFactory.create_agent(
            config=agent_config,
            flow_dir=flow_def.flow_dir or ""
        )
        
        # 创建节点函数
        node_name = node_def.name
        
        async def agent_node_action(state: FlowState) -> FlowState:
            """Agent节点函数"""
            # 构建系统消息（自动替换占位符，内部从 state 中提取 prompt_vars）
            sys_msg = build_system_message(
                prompt_cache_key=agent_executor.prompt_cache_key,
                state=state
            )
            
            # 拼装消息列表：history_messages + current_message
            history_messages = state.get("history_messages", [])
            current_message = state.get("current_message")
            
            # 构建消息列表
            msgs = history_messages.copy()
            if current_message:
                msgs.append(current_message)
            
            # 如果消息列表为空，直接返回
            if not msgs:
                logger.warning(f"[节点 {node_name}] 消息列表为空，跳过执行")
                return state
            
            # 执行Agent，传入消息列表和系统消息
            result = await agent_executor.ainvoke(
                msgs=msgs,
                callbacks=None,
                sys_msg=sys_msg
            )
            
            # 更新状态
            new_state = state.copy()
            
            # 关键：每次创建新 state 时，edges_var 使用新字典，不继承原始值
            # 确保上游节点的数据不会污染下游节点的条件判断
            new_state["edges_var"] = {}
            
            if "output" in result:
                # AgentExecutor返回output字段
                output = result["output"]
                
                # 通用化数据提取：不区分节点名称，统一处理所有节点
                # 检查两个数据来源：JSON所有属性 + additional_fields
                try:
                    if isinstance(output, str):
                        # 尝试从输出中提取 JSON
                        json_start = output.find("{")
                        json_end = output.rfind("}") + 1
                        if json_start >= 0 and json_end > json_start:
                            json_str = output[json_start:json_end]
                            output_data = json.loads(json_str)
                            
                            # 数据来源1：如果是 JSON 类型，直接将所有属性存储到 edges_var
                            # 跳过非边条件判断相关的字段（如 response_content, reasoning_summary, additional_fields）
                            if isinstance(output_data, dict):
                                for key, value in output_data.items():
                                    if key not in ["response_content", "reasoning_summary", "additional_fields"]:
                                        new_state["edges_var"][key] = value
                            
                            # 数据来源2：如果存在 additional_fields，将其中的所有字段也存储到 edges_var
                            if "additional_fields" in output_data:
                                additional_fields = output_data["additional_fields"]
                                if isinstance(additional_fields, dict):
                                    for key, value in additional_fields.items():
                                        new_state["edges_var"][key] = value
                            
                            logger.debug(
                                f"[节点 {node_name}] 从输出提取数据到 edges_var: {new_state['edges_var']}"
                            )
                except Exception as e:
                    logger.debug(f"[节点 {node_name}] 解析输出 JSON 失败（可能不是 JSON 格式）: {e}")
                    # 不是 JSON 格式或解析失败，不影响流程继续
                
                # 将AI回复存放到 flow_msgs（流程中间消息），不存放到 history_messages
                ai_message = AIMessage(content=output)
                flow_msgs = state.get("flow_msgs", [])
                new_flow_msgs = flow_msgs.copy()
                new_flow_msgs.append(ai_message)
                new_state["flow_msgs"] = new_flow_msgs
                # history_messages 保持不变，不添加中间节点的输出
            
            return new_state
        
        return agent_node_action

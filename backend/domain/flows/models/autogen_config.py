"""
AutoGen Team 节点配置模型

对应 YAML nodes[].type == autogen_team 的 config 结构。
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from backend.domain.flows.models.definition import ModelConfig

# 首期仅实现 round_robin；其它枚举值在 Creator 内拒绝
SUPPORTED_TEAM_MODES = frozenset({"round_robin"})


class AutogenAgentSpec(BaseModel):
    """Team 内单个参与者配置。"""

    name: str = Field(description="Agent 名称，须在 Team 内唯一")
    system_prompt: str = Field(description="系统提示词路径（相对于流程目录）")
    tools: List[str] = Field(default_factory=list, description="tool_registry 中的工具名")


class AutogenTerminationConfig(BaseModel):
    """终止条件：text_mention 与 max_messages 同时生效（OR）。"""

    text_mention: str = Field(
        default="APPROVE",
        description="出现该子串则停止（通常由 critic 发出）",
    )
    max_messages: int = Field(
        ...,
        ge=2,
        le=64,
        description="硬上限，生产必填",
    )


class AutogenTaskConfig(BaseModel):
    """任务拼装配置。"""

    template: Optional[str] = Field(
        default=None,
        description="可选模板；支持 {user_message}。为空则使用 current_message.content",
    )
    include_prompt_vars_keys: Optional[List[str]] = Field(
        default=None,
        description="从 prompt_vars 选取的 key 列表；None 表示不附加",
    )


class AutogenOutputConfig(BaseModel):
    """写回 FlowState 的策略。"""

    write_to_flow_msgs: bool = Field(default=True)
    edges_var_key: str = Field(
        default="review_approved",
        description="写入「是否批准」布尔值的 edges_var key",
    )
    persist_transcript: bool = Field(default=False)
    max_transcript_messages: int = Field(default=20, ge=1, le=100)
    content_max_chars: int = Field(
        default=8000,
        ge=256,
        description="写入 flow_msgs / transcript 的单条正文截断上限",
    )


class AutogenTeamNodeConfig(BaseModel):
    """YAML nodes[].config 对应结构（type=autogen_team）。"""

    team_mode: Literal["round_robin", "selector", "swarm"] = Field(
        default="round_robin",
    )
    model: ModelConfig = Field(description="全 Team 共用模型（首期简化）")
    agents: List[AutogenAgentSpec] = Field(min_length=2)
    termination: AutogenTerminationConfig
    timeout_seconds: int = Field(default=120, ge=10, le=1800)
    task: AutogenTaskConfig = Field(default_factory=AutogenTaskConfig)
    output: AutogenOutputConfig = Field(default_factory=AutogenOutputConfig)
    persist_to_persistence_edges_var: Optional[List[str]] = Field(
        default=None,
        description="执行后从 edges_var 同步到 persistence_edges_var 的 key 列表",
    )

    @model_validator(mode="after")
    def validate_agent_names_unique(self) -> "AutogenTeamNodeConfig":
        """
        校验 agents.name 唯一。

        Returns:
            通过校验的配置自身

        Raises:
            ValueError: agents.name 重复
        """
        names = [a.name for a in self.agents]
        if len(names) != len(set(names)):
            raise ValueError("agents.name 必须唯一")
        return self

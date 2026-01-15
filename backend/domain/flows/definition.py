"""
流程定义类
定义流程的结构和配置
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class ModelConfig(BaseModel):
    """模型配置"""
    provider: str = Field(description="模型供应商名称")
    name: str = Field(description="模型名称")
    temperature: float = Field(default=0.7, description="温度参数")
    thinking: Optional[Dict[str, str]] = Field(
        default=None,
        description="思考模式配置：{'type': 'enabled'}、{'type': 'disabled'} 或 {'type': 'auto'}"
    )
    reasoning_effort: Optional[str] = Field(
        default=None,
        description="推理努力程度：'minimal'、'low'、'medium'、'high'"
    )
    timeout: Optional[int] = Field(
        default=None,
        description="超时时间（秒），深度思考时建议设置为 1800（30分钟）"
    )
    
    @field_validator('thinking')
    @classmethod
    def validate_thinking(cls, v):
        """验证 thinking 参数格式"""
        if v is not None:
            if not isinstance(v, dict):
                raise ValueError("thinking 必须是字典类型")
            if "type" not in v:
                raise ValueError("thinking 必须包含 'type' 字段")
            if v["type"] not in ["enabled", "disabled", "auto"]:
                raise ValueError(f"thinking.type 必须是 'enabled'、'disabled' 或 'auto'，当前值: {v['type']}")
        return v
    
    @field_validator('reasoning_effort')
    @classmethod
    def validate_reasoning_effort(cls, v):
        """验证 reasoning_effort 参数值"""
        if v is not None and v not in ['minimal', 'low', 'medium', 'high']:
            raise ValueError(
                f"reasoning_effort 必须是 'minimal'、'low'、'medium' 或 'high'，当前值: {v}"
            )
        return v
    
    @model_validator(mode='after')
    def validate_dependencies(self):
        """验证参数依赖关系"""
        if self.thinking and self.reasoning_effort:
            thinking_type = self.thinking.get("type")
            if thinking_type == "disabled" and self.reasoning_effort != "minimal":
                raise ValueError(
                    f"当 thinking.type = 'disabled' 时，reasoning_effort 只能是 'minimal'，"
                    f"当前值: {self.reasoning_effort}"
                )
            if thinking_type == "enabled" and self.reasoning_effort == "minimal":
                raise ValueError(
                    f"当 thinking.type = 'enabled' 时，reasoning_effort 不能是 'minimal'，"
                    f"只能是 'low'、'medium' 或 'high'"
                )
        return self


class AgentNodeConfig(BaseModel):
    """Agent节点配置"""
    prompt: str = Field(description="提示词路径（相对于流程目录）")
    model: ModelConfig = Field(description="模型配置")
    tools: Optional[List[str]] = Field(default=None, description="工具列表")


class NodeDefinition(BaseModel):
    """节点定义"""
    name: str = Field(description="节点名称")
    type: str = Field(description="节点类型（agent、condition等）")
    config: Dict[str, Any] = Field(description="节点配置")


class EdgeDefinition(BaseModel):
    """边定义"""
    from_node: str = Field(alias="from", description="起始节点名称")
    to_node: str = Field(alias="to", description="目标节点名称")
    condition: str = Field(description="路由条件")


class FlowDefinition(BaseModel):
    """流程定义"""
    name: str = Field(description="流程名称")
    version: str = Field(description="流程版本")
    description: Optional[str] = Field(default=None, description="流程描述")
    nodes: List[NodeDefinition] = Field(description="节点列表")
    edges: List[EdgeDefinition] = Field(description="边列表")
    entry_node: str = Field(description="入口节点名称")
    flow_dir: Optional[str] = Field(default=None, description="流程目录路径（用于解析相对路径）")


class FlowPreviewInfo(FlowDefinition):
    """流程预览信息（继承FlowDefinition，增加预览相关属性）"""
    is_compiled: bool = Field(default=False, description="是否已编译")
    preview_image_path: Optional[str] = Field(default=None, description="流程图预览图片路径（相对于static目录）")


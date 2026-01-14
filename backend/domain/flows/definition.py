"""
流程定义类
定义流程的结构和配置
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """模型配置"""
    provider: str = Field(description="模型供应商名称")
    name: str = Field(description="模型名称")
    temperature: float = Field(default=0.7, description="温度参数")


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


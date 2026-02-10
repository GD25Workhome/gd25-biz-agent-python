"""
数据清洗相关 Schema
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from decimal import Decimal
from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_serializer


# ---------- DataSetsPath ----------
class DataSetsPathCreate(BaseModel):
    """创建数据集合文件夹"""

    id: str = Field(..., description="可主动设置的 id")
    id_path: Optional[str] = Field(None, description="上级路径")
    name: str = Field(..., max_length=200, description="名称")
    description: Optional[str] = Field(None, description="描述")
    metadata: Optional[dict] = Field(None, description="扩展元数据")


class DataSetsPathUpdate(BaseModel):
    """更新数据集合文件夹"""

    id_path: Optional[str] = Field(None, description="上级路径")
    name: Optional[str] = Field(None, max_length=200, description="名称")
    description: Optional[str] = Field(None, description="描述")
    metadata: Optional[dict] = Field(None, description="扩展元数据")


class DataSetsPathResponse(BaseModel):
    """数据集合文件夹响应"""

    id: str
    id_path: Optional[str] = None
    name: str
    description: Optional[str] = None
    metadata: Optional[dict] = Field(None, validation_alias="metadata_")
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class DataSetsPathTreeNode(BaseModel):
    """树形节点（用于树形列表）"""

    id: str
    id_path: Optional[str] = None
    name: str
    description: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    children: List["DataSetsPathTreeNode"] = Field(default_factory=list)


# ---------- DataSets ----------
class DataSetsCreate(BaseModel):
    """创建数据集合"""

    name: str = Field(..., max_length=200, description="名称")
    path_id: Optional[str] = Field(None, description="关联 dataSetsPath.id")
    input_schema: Optional[dict] = Field(None, description="input 的 JSON Schema")
    output_schema: Optional[dict] = Field(None, description="output 的 JSON Schema")
    metadata: Optional[dict] = Field(None, description="扩展元数据")


class DataSetsUpdate(BaseModel):
    """更新数据集合"""

    name: Optional[str] = Field(None, max_length=200, description="名称")
    path_id: Optional[str] = Field(None, description="关联 dataSetsPath.id")
    input_schema: Optional[dict] = Field(None, description="input 的 JSON Schema")
    output_schema: Optional[dict] = Field(None, description="output 的 JSON Schema")
    metadata: Optional[dict] = Field(None, description="扩展元数据")


class DataSetsResponse(BaseModel):
    """数据集合响应"""

    id: str
    name: str
    path_id: Optional[str] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    metadata: Optional[dict] = Field(None, validation_alias="metadata_")
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class DataSetsListResponse(BaseModel):
    """数据集合列表响应"""

    total: int = Field(description="总条数")
    items: List[DataSetsResponse] = Field(default_factory=list, description="当前页数据")


# ---------- DataSetsItems ----------
class DataSetsItemsCreate(BaseModel):
    """创建数据项"""

    unique_key: Optional[str] = Field(None, max_length=200, description="业务唯一 key")
    input: Optional[dict] = Field(None, description="输入数据")
    output: Optional[dict] = Field(None, description="输出数据")
    metadata: Optional[dict] = Field(None, description="扩展元数据")
    status: int = Field(1, description="1=激活，0=废弃")
    source: Optional[str] = Field(None, max_length=200, description="来源")


class DataSetsItemsUpdate(BaseModel):
    """更新数据项"""

    unique_key: Optional[str] = Field(None, max_length=200, description="业务唯一 key")
    input: Optional[dict] = Field(None, description="输入数据")
    output: Optional[dict] = Field(None, description="输出数据")
    metadata: Optional[dict] = Field(None, description="扩展元数据")
    status: Optional[int] = Field(None, description="1=激活，0=废弃")
    source: Optional[str] = Field(None, max_length=200, description="来源")


class DataSetsItemsResponse(BaseModel):
    """数据项响应"""

    id: str
    dataset_id: str
    unique_key: Optional[str] = None
    input: Optional[dict] = None
    output: Optional[dict] = None
    metadata: Optional[dict] = Field(None, validation_alias="metadata_")
    status: int
    source: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        populate_by_name = True


class DataSetsItemsListResponse(BaseModel):
    """数据项列表响应"""

    total: int = Field(description="总条数")
    items: List[DataSetsItemsResponse] = Field(default_factory=list, description="当前页数据")


# ---------- ImportConfig ----------
class ImportConfigCreate(BaseModel):
    """创建导入配置"""

    name: str = Field(..., max_length=200, description="配置名称")
    description: Optional[str] = Field(None, description="描述")
    import_config: Optional[dict] = Field(None, description="导入逻辑配置")


class ImportConfigUpdate(BaseModel):
    """更新导入配置"""

    name: Optional[str] = Field(None, max_length=200, description="配置名称")
    description: Optional[str] = Field(None, description="描述")
    import_config: Optional[dict] = Field(None, description="导入逻辑配置")


class ImportConfigResponse(BaseModel):
    """导入配置响应"""

    id: str
    name: str
    description: Optional[str] = None
    import_config: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ImportConfigListResponse(BaseModel):
    """导入配置列表响应"""

    total: int = Field(description="总条数")
    items: List[ImportConfigResponse] = Field(default_factory=list, description="当前页数据")


# 解决前向引用
DataSetsPathTreeNode.model_rebuild()


# ---------- DataItemsRewritten（改写后数据项，Step02 数据清洗管理）----------
class DataItemsRewrittenUpdate(BaseModel):
    """更新改写后数据项"""

    scenario_description: Optional[str] = Field(None, description="场景描述")
    rewritten_question: Optional[str] = Field(None, description="改写后的问题")
    rewritten_answer: Optional[str] = Field(None, description="改写后的回答")
    rewritten_rule: Optional[str] = Field(None, description="改写后的规则")
    source_dataset_id: Optional[str] = Field(None, max_length=100, description="来源 dataSets.id")
    source_item_id: Optional[str] = Field(None, max_length=100, description="来源 dataItems.id")
    scenario_type: Optional[str] = Field(None, max_length=1000, description="场景类型")
    sub_scenario_type: Optional[str] = Field(None, max_length=1000, description="子场景类型")
    rewrite_basis: Optional[str] = Field(None, description="改写依据")
    scenario_confidence: Optional[float] = Field(None, description="场景置信度（0-1）")
    trace_id: Optional[str] = Field(None, max_length=100, description="流程执行 traceId")
    batch_code: Optional[str] = Field(None, max_length=100, description="批次code")
    status: Optional[str] = Field(None, max_length=20, description="执行状态：success / failed")
    execution_metadata: Optional[dict] = Field(None, description="执行过程元数据")
    ai_tags: Optional[dict] = Field(None, description="AI 标签")
    ai_score: Optional[float] = Field(None, description="AI 评分")
    ai_score_metadata: Optional[dict] = Field(None, description="AI 评分元数据")
    manual_score: Optional[float] = Field(None, description="人工评分")
    manual_score_metadata: Optional[dict] = Field(None, description="人工评分元数据")


class DataItemsRewrittenResponse(BaseModel):
    """改写后数据项响应"""

    id: str
    scenario_description: Optional[str] = None
    rewritten_question: Optional[str] = None
    rewritten_answer: Optional[str] = None
    rewritten_rule: Optional[str] = None
    source_dataset_id: Optional[str] = None
    source_item_id: Optional[str] = None
    scenario_type: Optional[str] = None
    sub_scenario_type: Optional[str] = None
    rewrite_basis: Optional[str] = None
    scenario_confidence: Optional[float] = None
    trace_id: Optional[str] = None
    batch_code: Optional[str] = None
    status: Optional[str] = None
    execution_metadata: Optional[dict] = None
    ai_tags: Optional[dict] = None
    ai_score: Optional[float] = None
    ai_score_metadata: Optional[dict] = None
    manual_score: Optional[float] = None
    manual_score_metadata: Optional[dict] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    @field_serializer("ai_score", "manual_score", "scenario_confidence")
    def serialize_decimal(self, v: Any) -> Optional[float]:
        """将 Decimal 转为 float 以便 JSON 序列化"""
        if v is not None and isinstance(v, Decimal):
            return float(v)
        return v

    class Config:
        from_attributes = True


class DataItemsRewrittenListResponse(BaseModel):
    """改写后数据项列表响应"""

    total: int = Field(description="总条数")
    items: List[DataItemsRewrittenResponse] = Field(
        default_factory=list, description="当前页数据"
    )


# ---------- 数据清洗执行（rewritten execute）----------
class RewrittenExecuteQueryParams(BaseModel):
    """数据清洗按条件查询参数（仅筛选，无分页）"""

    status: Optional[int] = Field(None, description="1=激活，0=废弃")
    unique_key: Optional[str] = Field(None, description="unique_key（包含）")
    source: Optional[str] = Field(None, description="source（包含）")
    keyword: Optional[str] = Field(None, description="关键词（在 input/output/metadata 中搜索）")


class RewrittenExecuteRequest(BaseModel):
    """数据清洗执行请求"""

    item_ids: Optional[List[str]] = Field(None, description="指定要清洗的数据项 ID 列表，若提供则忽略 query_params")
    query_params: Optional[RewrittenExecuteQueryParams] = Field(
        None, description="筛选条件，命中多少执行多少"
    )


class RewrittenExecuteStats(BaseModel):
    """数据清洗执行统计（旧接口兼容）"""

    total: int = Field(description="总条数")
    success: int = Field(description="成功条数")
    failed: int = Field(description="失败条数")


class RewrittenExecuteResponse(BaseModel):
    """数据清洗执行响应（批量创建模式）"""

    success: bool = Field(description="是否成功")
    message: str = Field(description="提示信息")
    batch_code: str = Field(description="批次编码")
    total: int = Field(description="创建的任务总数")

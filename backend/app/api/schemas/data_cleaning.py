"""
数据清洗相关 Schema
设计文档：cursor_docs/020401-数据导入管理模块技术设计.md
"""
from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, Field


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

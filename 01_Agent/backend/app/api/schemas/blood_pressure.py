"""
血压记录相关Schema
"""
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class BloodPressureRecordCreate(BaseModel):
    """创建血压记录请求"""
    user_id: str = Field(description="用户ID")
    systolic: int = Field(ge=50, le=250, description="收缩压（50-250 mmHg）")
    diastolic: int = Field(ge=30, le=200, description="舒张压（30-200 mmHg）")
    heart_rate: Optional[int] = Field(None, ge=30, le=200, description="心率（30-200 bpm）")
    record_time: Optional[datetime] = Field(None, description="记录时间")
    notes: Optional[str] = Field(None, description="备注")


class BloodPressureRecordUpdate(BaseModel):
    """更新血压记录请求"""
    systolic: Optional[int] = Field(None, ge=50, le=250, description="收缩压")
    diastolic: Optional[int] = Field(None, ge=30, le=200, description="舒张压")
    heart_rate: Optional[int] = Field(None, ge=30, le=200, description="心率")
    record_time: Optional[datetime] = Field(None, description="记录时间")
    notes: Optional[str] = Field(None, description="备注")


class BloodPressureRecordResponse(BaseModel):
    """血压记录响应"""
    id: str
    user_id: str
    systolic: int
    diastolic: int
    heart_rate: Optional[int]
    record_time: Optional[datetime]
    notes: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True  # 允许从ORM模型创建


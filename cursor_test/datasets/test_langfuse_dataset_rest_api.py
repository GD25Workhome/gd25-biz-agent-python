"""
测试 Langfuse DataSet REST API 是否支持 inputSchema / expectedOutputSchema

调研结论：
- Langfuse 官方 REST API（POST /api/public/v2/datasets）支持 inputSchema 和 expectedOutputSchema
- 认证方式：Basic Auth（username=Public Key, password=Secret Key）
- 当前 Python SDK 3.7.0 的 create_dataset 不支持 input_schema/expected_output_schema 参数
- 可通过直接调用 REST API 绕过 SDK 限制，实现自动化 Schema 设置

运行方式（需配置 .env 中的 LANGFUSE_*）：
    cd 项目根目录
    python -m cursor_test.datasets.test_langfuse_dataset_rest_api

或：
    python cursor_test/datasets/test_langfuse_dataset_rest_api.py
"""
import json
import os
import sys
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

import requests

# 测试用 Dataset 名称（与接入指南示例一致，加后缀区分 REST 测试）
DATASET_NAME = "rest-api-schema-test-dataset"

# 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_SCHEMA_PATH = _PROJECT_ROOT / "doc" / "总体设计规划" / "数据归档-schema" / "DataSet-input-schema.json"
OUTPUT_SCHEMA_PATH = _PROJECT_ROOT / "doc" / "总体设计规划" / "数据归档-schema" / "DataSet-output-schema.json"


def get_langfuse_config() -> tuple:
    """从环境变量获取 Langfuse 配置"""
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
    if not public_key or not secret_key:
        raise ValueError(
            "请配置 .env 中的 LANGFUSE_PUBLIC_KEY 和 LANGFUSE_SECRET_KEY。"
            "可在 Langfuse 项目设置中获取 API Keys。"
        )
    return public_key, secret_key, host


def load_schema(path: Path) -> dict:
    """加载 JSON Schema 文件"""
    if not path.exists():
        raise FileNotFoundError(f"Schema 文件不存在: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_dataset_via_rest(
    name: str,
    description: str,
    input_schema: Optional[dict],
    expected_output_schema: Optional[dict],
    metadata: Optional[dict] = None,
) -> dict:
    """
    通过 REST API 创建 DataSet（支持 inputSchema / expectedOutputSchema）

    Args:
        name: DataSet 名称
        description: 描述
        input_schema: Input JSON Schema（可选）
        expected_output_schema: Expected Output JSON Schema（可选）
        metadata: 元数据（可选）

    Returns:
        API 响应 JSON
    """
    public_key, secret_key, host = get_langfuse_config()
    url = f"{host}/api/public/v2/datasets"

    body: dict = {
        "name": name,
        "description": description or "",
    }
    if metadata:
        body["metadata"] = metadata
    if input_schema:
        body["inputSchema"] = input_schema
    if expected_output_schema:
        body["expectedOutputSchema"] = expected_output_schema

    resp = requests.post(
        url,
        auth=(public_key, secret_key),
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=30,
    )

    resp.raise_for_status()
    return resp.json()


def create_dataset_item_via_rest(
    dataset_name: str,
    input_data: dict,
    expected_output: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """
    通过 REST API 创建 DataSet Item

    Args:
        dataset_name: DataSet 名称
        input_data: input 数据
        expected_output: 预期输出（可选）
        metadata: 元数据（可选）

    Returns:
        API 响应 JSON
    """
    public_key, secret_key, host = get_langfuse_config()
    url = f"{host}/api/public/dataset-items"

    body: dict = {
        "datasetName": dataset_name,
        "input": input_data,
    }
    if expected_output is not None:
        body["expectedOutput"] = expected_output
    if metadata:
        body["metadata"] = metadata

    resp = requests.post(
        url,
        auth=(public_key, secret_key),
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=30,
    )

    resp.raise_for_status()
    return resp.json()


def get_dataset_via_rest(dataset_name: str) -> dict:
    """通过 REST API 获取 DataSet（验证 inputSchema/expectedOutputSchema 是否已设置）"""
    public_key, secret_key, host = get_langfuse_config()
    # dataset name 可能包含 /，需要 URL 编码
    import urllib.parse
    encoded_name = urllib.parse.quote(dataset_name, safe="")
    url = f"{host}/api/public/v2/datasets/{encoded_name}"

    resp = requests.get(
        url,
        auth=(public_key, secret_key),
        timeout=30,
    )

    resp.raise_for_status()
    return resp.json()


def main() -> None:
    print("=" * 60)
    print("Langfuse DataSet REST API 测试（inputSchema / expectedOutputSchema）")
    print("=" * 60)

    # 1. 加载 Schema
    print("\n1. 加载 Schema 文件")
    try:
        input_schema = load_schema(INPUT_SCHEMA_PATH)
        output_schema = load_schema(OUTPUT_SCHEMA_PATH)
        print(f"   Input Schema: {INPUT_SCHEMA_PATH.name}")
        print(f"   Output Schema: {OUTPUT_SCHEMA_PATH.name}")
    except FileNotFoundError as e:
        print(f"   错误: {e}")
        print("   使用简化 Schema 进行测试")
        input_schema = {
            "type": "object",
            "properties": {"current_msg": {"type": "string"}},
            "required": ["current_msg"],
        }
        output_schema = {
            "type": "object",
            "properties": {"response_message": {"type": "string"}},
            "required": ["response_message"],
        }

    # 2. 通过 REST API 创建 DataSet（带 Schema）
    print("\n2. 通过 REST API 创建 DataSet（含 inputSchema/expectedOutputSchema）")
    try:
        result = create_dataset_via_rest(
            name=DATASET_NAME,
            description="REST API 测试：验证 inputSchema/expectedOutputSchema 支持",
            input_schema=input_schema,
            expected_output_schema=output_schema,
            metadata={"test_source": "test_langfuse_dataset_rest_api.py"},
        )
        print(f"   创建成功: {result.get('name', DATASET_NAME)}")
        print(f"   响应: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}...")
    except requests.exceptions.HTTPError as e:
        print(f"   错误: {e}")
        if e.response is not None:
            print(f"   响应: {e.response.text[:500]}")
        return
    except Exception as e:
        print(f"   错误: {e}")
        return

    # 3. 获取 DataSet 验证 Schema 是否已设置
    print("\n3. 获取 DataSet 验证 Schema 是否已设置")
    try:
        dataset = get_dataset_via_rest(DATASET_NAME)
        has_input = "inputSchema" in dataset and dataset["inputSchema"] is not None
        has_output = "expectedOutputSchema" in dataset and dataset["expectedOutputSchema"] is not None
        print(f"   inputSchema 已设置: {has_input}")
        print(f"   expectedOutputSchema 已设置: {has_output}")
        if has_input:
            print(f"   inputSchema 预览: {json.dumps(dataset['inputSchema'], ensure_ascii=False)[:200]}...")
        if has_output:
            print(f"   expectedOutputSchema 预览: {json.dumps(dataset['expectedOutputSchema'], ensure_ascii=False)[:200]}...")
    except Exception as e:
        print(f"   获取失败: {e}")

    # 4. 创建一条符合 Schema 的 Item
    print("\n4. 创建 DataSet Item（验证 Schema 校验）")
    try:
        item = create_dataset_item_via_rest(
            dataset_name=DATASET_NAME,
            input_data={"current_msg": "测试消息"},
            expected_output={"response_message": "测试回复"},
            metadata={"message_id": "test-001"},
        )
        print(f"   Item 创建成功: id={item.get('id', 'N/A')}")
    except requests.exceptions.HTTPError as e:
        print(f"   错误: {e}")
        if e.response is not None:
            print(f"   响应: {e.response.text[:500]}")
        return
    except Exception as e:
        print(f"   错误: {e}")
        return

    print("\n" + "=" * 60)
    print("测试完成。请在 Langfuse UI 中查看 DataSet 的 Schema Validation 区域。")
    print("=" * 60)


if __name__ == "__main__":
    main()

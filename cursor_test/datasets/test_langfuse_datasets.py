"""
测试 Langfuse Datasets 的创建、添加 Item 与获取。

实现步骤：
1. 创建 Dataset（create_dataset）
2. 向 Dataset 新增 3 条 Item（create_dataset_item）
3. 获取 Dataset 并遍历 items（get_dataset）

运行方式（需先启动本地 Langfuse，并配置 .env 中的 LANGFUSE_*）：
    cd 项目根目录
    python -m cursor_test.datasets.test_langfuse_datasets

或：
    python cursor_test/datasets/test_langfuse_datasets.py
"""
import sys
from pathlib import Path

# 添加项目根目录到路径（当前文件在 cursor_test/datasets/ 下）
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(project_root / ".env")

from langfuse import Langfuse


# 测试用 Dataset 名称（与接入指南示例一致）
DATASET_NAME = "qa-evaluation-dataset"


def main() -> None:
    # 通过环境变量 LANGFUSE_PUBLIC_KEY、LANGFUSE_SECRET_KEY、LANGFUSE_HOST 初始化
    langfuse = Langfuse()

    # 1. 创建 Dataset
    print("=" * 60)
    print("1. 创建 Dataset")
    print("=" * 60)
    langfuse.create_dataset(
        name=DATASET_NAME,
        description="QA 评估数据集",
        metadata={
            "author": "Alice",
            "date": "2025-02-02",
            "type": "benchmark",
        },
    )
    print(f"已创建/更新 Dataset: {DATASET_NAME}\n")

    # 2. 新增 3 条 Dataset Item
    print("=" * 60)
    print("2. 新增 3 条 Dataset Item")
    print("=" * 60)
    items = [
        {
            "input": {"text": "hello world"},
            "expected_output": {"text": "hello world"},
            "metadata": {"model": "llama3"},
        },
        {
            "input": {"text": "What is 2+2?"},
            "expected_output": {"text": "4"},
            "metadata": {"model": "gpt-4"},
        },
        {
            "input": {"text": "Translate: Hello"},
            "expected_output": {"text": "你好"},
            "metadata": {"model": "claude"},
        },
    ]
    for i, item in enumerate(items, 1):
        langfuse.create_dataset_item(
            dataset_name=DATASET_NAME,
            input=item["input"],
            expected_output=item["expected_output"],
            metadata=item["metadata"],
        )
        print(f"  已添加第 {i} 条: input={item['input']}")
    print()

    # # 确保异步写入完成
    # langfuse.flush()

    # # 3. 获取 Dataset 并遍历 items
    # print("=" * 60)
    # print("3. 获取 Dataset 并遍历 items")
    # print("=" * 60)
    # dataset = langfuse.get_dataset(DATASET_NAME)
    # items_list = list(dataset.items)
    # for idx, item in enumerate(items_list, 1):
    #     print(f"  Item {idx}: input={item.input}, expected_output={item.expected_output}")
    # print(f"\n共获取 {len(items_list)} 条 Item（若 Dataset 中已有历史数据，会多于本次新增的 3 条）。")
    # print("=" * 60)
    # print("测试完成。")
    # print("=" * 60)


if __name__ == "__main__":
    main()

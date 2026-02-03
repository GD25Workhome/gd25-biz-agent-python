"""
Feishu Excel 导入 Langfuse Datasets 配置类

所有运行参数在此配置，无需通过命令行传递。
"""
from pathlib import Path
from typing import Dict, List

# 项目根目录（scripts/import_to_datasets/feishu_ceshi_case 的上级四级）
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class Config:
    """导入脚本配置类"""

    # ---------- 数据源配置 ----------
    # Excel 所在目录（相对于项目根）
    data_dir: Path = _PROJECT_ROOT / "static" / "rag_source" / "uat_data"

    # 要导入的 Excel 文件名列表
    excel_files: List[str] = [
        "4.1 lsk_副本.xlsx",
        # "sh-1128_副本.xlsx",
    ]

    # 仅处理指定 Excel 下的指定 Sheet：key 为 excelName（不含扩展名），value 为要处理的 sheet 名称列表
    # 为空时：处理 excel_files 中所有 Excel 的所有 sheet
    # 非空时：仅处理映射中的 Excel，且只处理其下列出的 sheet；未在映射中的 Excel 整体跳过
    # 示例：{"sh-1128_副本": ["常见问题及单轮"]} → 只处理 sh-1128_副本 的「常见问题及单轮」一个 sheet，4.1 lsk_副本 整体跳过
    sheet_include_mapping: Dict[str, List[str]] = {}
    # sheet_include_mapping: Dict[str, List[str]] = {"sh-1128_副本": ["常见问题及单轮"]}
    # sheet_include_mapping: Dict[str, List[str]] = {"sh-1128_副本": ["患者无数据+历史会话+历史Action"]}
    # sheet_include_mapping: Dict[str, List[str]] = {"4.1 lsk_副本": ["患者有数据（无历史会话，无历史action）"]}
    

    # ---------- DataSet 配置 ----------
    # DataSet 名称前缀，完整格式为 {prefix}/{excelName}/{sheetName}
    dataset_name_prefix: str = "feishu"

    # Input/Output JSON Schema 文件路径（相对于项目根）
    input_schema_path: Path = _PROJECT_ROOT / "doc" / "总体设计规划" / "数据归档-schema" / "DataSet-input-schema.json"
    output_schema_path: Path = _PROJECT_ROOT / "doc" / "总体设计规划" / "数据归档-schema" / "DataSet-output-schema.json"

    # ---------- 解析策略配置 ----------
    # 默认解析策略类型（当 sheet 未在 sheet_parser_mapping、excel_parser_mapping 中指定时使用）
    default_parser_type: str = "lsk"

    # 按 Excel 的默认解析策略：key 为 excelName（不含扩展名），value 为 parser_type
    excel_parser_mapping: Dict[str, str] = {
        "4.1 lsk_副本": "lsk",
        "sh-1128_副本": "sh1128",
    }

    # Sheet 级解析策略覆盖：key 为 "excelName/sheetName"，value 为 parser_type
    # 优先于 excel_parser_mapping，用于同一 Excel 内不同 Sheet 使用不同策略
    sheet_parser_mapping: Dict[str, str] = {
        "sh-1128_副本/常见问题及单轮": "sh1128_multi",  # 多轮 Q/A 拆分，一行→多 Item
        "sh-1128_副本/患者无数据+历史会话+历史Action": "sh1128_history_qa",  # 历史会话 Q/A 解析
    }

    # ---------- 重复导入配置 ----------
    # 是否在导入前清空 DataSet 中已有 Items（实现重复导入时覆盖而非追加）
    clear_before_import: bool = True

    # ---------- 脚本元信息（写入 DataSet metadata） ----------
    script_name: str = "feishu_ceshi_case_create_datasets"
    import_version: str = "v1.0"

    @classmethod
    def get_dataset_name(cls, excel_name: str, sheet_name: str) -> str:
        """
        生成 DataSet 完整名称

        Args:
            excel_name: Excel 文件名（不含扩展名）
            sheet_name: Sheet 名称

        Returns:
            str: 格式为 {prefix}/{excelName}/{sheetName}
        """
        return f"{cls.dataset_name_prefix}/{excel_name}/{sheet_name}"

    @classmethod
    def get_parser_type(cls, excel_name: str, sheet_name: str) -> str:
        """
        根据 Excel 名和 Sheet 名获取解析策略类型

        优先级：sheet_parser_mapping > excel_parser_mapping > default_parser_type

        Args:
            excel_name: Excel 文件名（不含扩展名）
            sheet_name: Sheet 名称

        Returns:
            str: 解析策略类型
        """
        sheet_key = f"{excel_name}/{sheet_name}"
        if sheet_key in cls.sheet_parser_mapping:
            return cls.sheet_parser_mapping[sheet_key]
        if excel_name in cls.excel_parser_mapping:
            return cls.excel_parser_mapping[excel_name]
        return cls.default_parser_type

    @classmethod
    def get_excel_path(cls, filename: str) -> Path:
        """获取 Excel 文件的完整路径"""
        return cls.data_dir / filename

    @classmethod
    def should_process_excel(cls, excel_name: str) -> bool:
        """
        判断是否应处理该 Excel 文件

        当 sheet_include_mapping 非空时，仅处理映射中的 Excel；未在映射中的 Excel 整体跳过。

        Args:
            excel_name: Excel 文件名（不含扩展名）

        Returns:
            bool: True 表示处理该 Excel，False 表示跳过
        """
        if not cls.sheet_include_mapping:
            return True
        return excel_name in cls.sheet_include_mapping

    @classmethod
    def should_process_sheet(cls, excel_name: str, sheet_name: str) -> bool:
        """
        判断是否应处理该 Sheet

        Args:
            excel_name: Excel 文件名（不含扩展名）
            sheet_name: Sheet 名称

        Returns:
            bool: True 表示处理，False 表示跳过
        """
        if not cls.sheet_include_mapping:
            return True
        if excel_name not in cls.sheet_include_mapping:
            return False  # 未在映射中的 Excel 已由 should_process_excel 跳过，此处不应到达
        return sheet_name in cls.sheet_include_mapping[excel_name]

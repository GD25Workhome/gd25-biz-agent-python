"""
RAG数据导入命令行脚本

功能：从Excel文件导入数据到向量库

使用方法：
    python scripts/import_rag_data.py --excel <excel_path> [--clear] [--log-level <level>]

示例：
    # 从项目根目录的相对路径（推荐）
    python scripts/import_rag_data.py --excel static/rag_source/第二步格式化/提示词案例库.xlsx
    python scripts/import_rag_data.py --excel static/rag_source/第二步格式化/提示词案例库.xlsx --clear
    python scripts/import_rag_data.py --excel static/rag_source/第二步格式化/提示词案例库.xlsx --log-level DEBUG
    
    # 或使用绝对路径
    python scripts/import_rag_data.py --excel /absolute/path/to/提示词案例库.xlsx
"""
import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.rag.data_import import DataImporter


def setup_logging(log_level: str = "INFO"):
    """
    配置日志
    
    Args:
        log_level: 日志级别（DEBUG, INFO, WARNING, ERROR）
    """
    # 配置日志格式
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    # 设置日志级别
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # 配置根日志记录器
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )


def parse_arguments():
    """
    解析命令行参数
    
    Returns:
        argparse.Namespace: 解析后的参数
    """
    parser = argparse.ArgumentParser(
        description="从Excel文件导入数据到RAG向量库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 基本导入
  python scripts/import_rag_data.py --excel data.xlsx
  
  # 导入前清空现有数据
  python scripts/import_rag_data.py --excel data.xlsx --clear
  
  # 使用DEBUG日志级别
  python scripts/import_rag_data.py --excel data.xlsx --log-level DEBUG
        """
    )
    
    parser.add_argument(
        "--excel",
        type=str,
        required=True,
        help="Excel文件路径（支持相对路径和绝对路径）"
    )
    
    parser.add_argument(
        "--clear",
        action="store_true",
        help="导入前清空现有数据（默认：否）"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认：INFO）"
    )
    
    return parser.parse_args()


def find_project_root() -> Path:
    """
    查找项目根目录（包含 .env 文件的目录）
    
    Returns:
        Path: 项目根目录路径
    """
    current = Path(__file__).resolve()
    # 当前文件位于 scripts/import_rag_data.py，项目根目录应该是 current.parent
    project_root = current.parent
    
    # 验证项目根目录是否存在 .env 文件
    env_file = project_root / ".env"
    if env_file.exists():
        return project_root
    
    # 如果项目根目录没有 .env，向上查找
    for parent in current.parents:
        env_file = parent / ".env"
        if env_file.exists():
            return parent
    
    # 如果都找不到，返回计算出的项目根目录（可能 .env 文件不存在）
    return project_root


def validate_excel_file(excel_path: Path) -> bool:
    """
    验证Excel文件
    
    Args:
        excel_path: Excel文件路径
        
    Returns:
        bool: 是否有效
    """
    if not excel_path.exists():
        print(f"✗ 错误：Excel文件不存在: {excel_path}")
        return False
    
    if not excel_path.is_file():
        print(f"✗ 错误：路径不是文件: {excel_path}")
        return False
    
    if excel_path.suffix.lower() not in ['.xlsx', '.xls']:
        print(f"✗ 错误：文件格式不支持（仅支持 .xlsx 和 .xls）: {excel_path}")
        return False
    
    return True


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 配置日志
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # 解析Excel文件路径
    excel_path = Path(args.excel)
    if not excel_path.is_absolute():
        # 相对路径：优先相对于项目根目录，如果不存在则相对于脚本所在目录
        project_root = find_project_root()
        project_path = (project_root / excel_path).resolve()
        
        if project_path.exists():
            excel_path = project_path
        else:
            # 如果项目根目录下不存在，尝试相对于脚本目录
            script_dir = Path(__file__).parent
            excel_path = (script_dir / excel_path).resolve()
    
    # 验证Excel文件
    if not validate_excel_file(excel_path):
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("RAG数据导入工具")
    logger.info("=" * 60)
    logger.info(f"Excel文件: {excel_path}")
    logger.info(f"清空现有数据: {'是' if args.clear else '否'}")
    logger.info(f"日志级别: {args.log_level}")
    logger.info("")
    
    # 导入数据
    try:
        # DataImporter会自动创建连接
        importer = DataImporter()
        results = importer.import_from_excel(
            excel_path,
            clear_existing=args.clear
        )
        
        # 打印详细结果
        logger.info("")
        logger.info("=" * 60)
        logger.info("导入结果详情")
        logger.info("=" * 60)
        for sheet_name, stats in results.items():
            logger.info(f"Sheet '{sheet_name}': 成功 {stats['success']} 条，失败 {stats['fail']} 条")
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✓ 数据导入完成")
        logger.info("=" * 60)
        
        # 如果有失败的数据，返回非零退出码
        total_fail = sum(r["fail"] for r in results.values())
        if total_fail > 0:
            logger.warning(f"⚠️  警告：有 {total_fail} 条数据导入失败")
            sys.exit(1)
        else:
            sys.exit(0)
    
    except KeyboardInterrupt:
        logger.warning("\n⚠️  用户中断操作")
        sys.exit(130)
    
    except Exception as e:
        logger.error(f"\n✗ 导入失败: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()

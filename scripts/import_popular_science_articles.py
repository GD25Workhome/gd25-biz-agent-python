"""
科普文章数据导入命令行脚本

功能：从CSV文件导入科普文章数据到向量库

使用方法：
    python scripts/import_popular_science_articles.py --csv <csv_path> [--clear] [--log-level <level>]

示例：
    # 从项目根目录的相对路径（推荐，注意使用引号包裹包含特殊字符的路径）
    python scripts/import_popular_science_articles.py --csv "static/rag_source/科普文章/科普文章(通用素材)-1126 - List.csv"
    python scripts/import_popular_science_articles.py --csv "static/rag_source/科普文章/科普文章(通用素材)-1126 - List.csv" --clear
    python scripts/import_popular_science_articles.py --csv "static/rag_source/科普文章/科普文章(通用素材)-1126 - List.csv" --log-level DEBUG
    
    # 或使用绝对路径
    python scripts/import_popular_science_articles.py --csv /absolute/path/to/data.csv
"""
import argparse
import logging
import sys
from pathlib import Path
from typing import List, Tuple

import pandas as pd
import psycopg

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.database.vector_connection import get_vector_db_connection
from backend.infrastructure.rag.data_import import EmbeddingModelCache
from backend.infrastructure.database.models.rag_models import PopularScienceArticle

# 配置日志
logger = logging.getLogger(__name__)


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
        description="从CSV文件导入科普文章数据到RAG向量库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 基本导入
  python scripts/import_popular_science_articles.py --csv data.csv
  
  # 导入前清空现有数据
  python scripts/import_popular_science_articles.py --csv data.csv --clear
  
  # 使用DEBUG日志级别
  python scripts/import_popular_science_articles.py --csv data.csv --log-level DEBUG
        """
    )
    
    parser.add_argument(
        "--csv",
        type=str,
        required=True,
        help="CSV文件路径（支持相对路径和绝对路径）"
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
    # 当前文件位于 scripts/import_popular_science_articles.py，项目根目录应该是 current.parent
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


def validate_csv_file(csv_path: Path) -> bool:
    """
    验证CSV文件
    
    Args:
        csv_path: CSV文件路径
        
    Returns:
        bool: 是否有效
    """
    if not csv_path.exists():
        print(f"✗ 错误：CSV文件不存在: {csv_path}")
        return False
    
    if not csv_path.is_file():
        print(f"✗ 错误：路径不是文件: {csv_path}")
        return False
    
    if csv_path.suffix.lower() != '.csv':
        print(f"✗ 错误：文件格式不支持（仅支持 .csv）: {csv_path}")
        return False
    
    return True


def read_csv_data(csv_path: Path) -> pd.DataFrame:
    """
    读取CSV文件数据
    
    Args:
        csv_path: CSV文件路径
        
    Returns:
        pd.DataFrame: 读取的数据
    """
    logger.info(f"正在读取CSV文件: {csv_path}")
    
    try:
        # 读取CSV文件，使用UTF-8编码
        df = pd.read_csv(csv_path, encoding='utf-8')
        logger.info(f"✓ 成功读取CSV文件，共 {len(df)} 行数据")
        return df
    except UnicodeDecodeError:
        # 如果UTF-8失败，尝试其他编码
        logger.warning("UTF-8编码失败，尝试GBK编码...")
        try:
            df = pd.read_csv(csv_path, encoding='gbk')
            logger.info(f"✓ 成功读取CSV文件（使用GBK编码），共 {len(df)} 行数据")
            return df
        except Exception as e:
            logger.error(f"读取CSV文件失败: {e}")
            raise
    except Exception as e:
        logger.error(f"读取CSV文件失败: {e}")
        raise


def parse_csv_data(df: pd.DataFrame) -> List[dict]:
    """
    解析CSV数据
    
    Args:
        df: DataFrame数据
        
    Returns:
        List[dict]: 解析后的数据列表
    """
    logger.info("正在解析CSV数据...")
    
    # 必需的列
    required_columns = ['文章素材ID', '文章标题', '文章详情内容']
    
    # 检查必需的列是否存在
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        logger.error(f"CSV文件缺少必需的列: {missing_columns}")
        logger.info(f"可用的列: {list(df.columns)}")
        raise ValueError(f"缺少必需的列: {missing_columns}")
    
    # 数据清洗和验证
    parsed_data = []
    for idx, row in df.iterrows():
        try:
            # 提取必需字段
            article_material_id = str(row['文章素材ID']).strip()
            article_title = str(row['文章标题']).strip() if pd.notna(row.get('文章标题')) else ""
            article_content = str(row['文章详情内容']).strip() if pd.notna(row.get('文章详情内容')) else ""
            
            # 验证必需字段不为空
            if not article_material_id:
                logger.warning(f"  第 {idx + 2} 行数据不完整（文章素材ID为空），跳过")
                continue
            
            if not article_title:
                logger.warning(f"  第 {idx + 2} 行数据不完整（文章标题为空），跳过")
                continue
            
            if not article_content:
                logger.warning(f"  第 {idx + 2} 行数据不完整（文章详情内容为空），跳过")
                continue
            
            parsed_data.append({
                'article_material_id': article_material_id,
                'article_title': article_title,
                'article_content': article_content,
            })
        
        except Exception as e:
            logger.warning(f"  第 {idx + 2} 行数据解析失败: {e}，跳过")
            continue
    
    logger.info(f"  ✓ 解析完成，有效数据: {len(parsed_data)} 条")
    return parsed_data


def clear_existing_data(conn: psycopg.Connection):
    """
    清空现有数据
    
    Args:
        conn: 数据库连接
    """
    logger.info("正在清空现有数据...")
    try:
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {PopularScienceArticle.__tablename__}")
            conn.commit()
        logger.info("✓ 现有数据已清空")
    except Exception as e:
        logger.error(f"清空数据失败: {e}")
        raise


def import_articles(
    csv_path: Path,
    clear_existing: bool = False,
    batch_size: int = 100
) -> Tuple[int, int]:
    """
    导入科普文章数据到数据库
    
    Args:
        csv_path: CSV文件路径
        clear_existing: 是否清空现有数据
        batch_size: 批处理大小
        
    Returns:
        Tuple[int, int]: (成功数量, 失败数量)
    """
    # 读取和解析CSV数据
    df = read_csv_data(csv_path)
    parsed_data = parse_csv_data(df)
    
    if not parsed_data:
        logger.warning("没有有效数据需要导入")
        return 0, 0
    
    # 获取数据库连接
    conn = get_vector_db_connection()
    
    try:
        # 如果指定清空现有数据
        if clear_existing:
            clear_existing_data(conn)
        
        # 初始化embedding模型
        embedding_cache = EmbeddingModelCache()
        logger.info("正在加载Embedding模型...")
        # 预加载模型
        _ = embedding_cache.get_model()
        
        # 批量插入数据
        logger.info(f"正在导入数据（批处理大小: {batch_size}）...")
        
        success_count = 0
        fail_count = 0
        
        # 分批处理
        for i in range(0, len(parsed_data), batch_size):
            batch = parsed_data[i:i + batch_size]
            batch_data = []
            
            for item in batch:
                try:
                    # 生成向量（基于文章标题）
                    embedding_vector = embedding_cache.text_to_embedding(item['article_title'])
                    
                    batch_data.append((
                        item['article_material_id'],
                        item['article_title'],
                        item['article_content'],
                        embedding_vector  # psycopg会自动转换为vector类型
                    ))
                except Exception as e:
                    logger.warning(f"  处理文章 '{item['article_material_id']}' 失败: {e}，跳过")
                    fail_count += 1
                    continue
            
            # 批量插入到数据库
            if batch_data:
                try:
                    with conn.cursor() as cur:
                        # 使用INSERT ... ON CONFLICT DO NOTHING避免重复插入
                        cur.executemany(
                            f"""
                            INSERT INTO {PopularScienceArticle.__tablename__}
                            (article_material_id, article_title, article_content, embedding)
                            VALUES (%s, %s, %s, %s::vector)
                            ON CONFLICT (article_material_id) DO UPDATE
                            SET article_title = EXCLUDED.article_title,
                                article_content = EXCLUDED.article_content,
                                embedding = EXCLUDED.embedding,
                                updated_at = NOW()
                            """,
                            batch_data
                        )
                        conn.commit()
                        success_count += len(batch_data)
                        logger.info(f"  ✓ 已导入 {success_count}/{len(parsed_data)} 条数据")
                except Exception as e:
                    logger.error(f"  批量插入失败: {e}")
                    conn.rollback()
                    fail_count += len(batch_data)
        
        logger.info(f"✓ 数据导入完成：成功 {success_count} 条，失败 {fail_count} 条")
        return success_count, fail_count
    
    finally:
        conn.close()


def main():
    """主函数"""
    # 解析命令行参数
    args = parse_arguments()
    
    # 配置日志
    setup_logging(args.log_level)
    logger = logging.getLogger(__name__)
    
    # 解析CSV文件路径
    csv_path = Path(args.csv)
    if not csv_path.is_absolute():
        # 相对路径：优先相对于项目根目录，如果不存在则相对于脚本所在目录
        project_root = find_project_root()
        project_path = (project_root / csv_path).resolve()
        
        if project_path.exists():
            csv_path = project_path
        else:
            # 如果项目根目录下不存在，尝试相对于脚本目录
            script_dir = Path(__file__).parent
            csv_path = (script_dir / csv_path).resolve()
    
    # 验证CSV文件
    if not validate_csv_file(csv_path):
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("科普文章数据导入工具")
    logger.info("=" * 60)
    logger.info(f"CSV文件: {csv_path}")
    logger.info(f"清空现有数据: {'是' if args.clear else '否'}")
    logger.info(f"日志级别: {args.log_level}")
    logger.info("")
    
    # 导入数据
    try:
        success_count, fail_count = import_articles(
            csv_path,
            clear_existing=args.clear
        )
        
        logger.info("")
        logger.info("=" * 60)
        logger.info("✓ 数据导入完成")
        logger.info("=" * 60)
        logger.info(f"成功: {success_count} 条")
        logger.info(f"失败: {fail_count} 条")
        
        # 如果有失败的数据，返回非零退出码
        if fail_count > 0:
            logger.warning(f"⚠️  警告：有 {fail_count} 条数据导入失败")
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

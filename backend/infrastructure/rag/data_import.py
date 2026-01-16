"""
RAG数据导入模块
实现从Excel文件导入数据到向量库的功能

功能包括：
1. Excel文件解析（按Sheet分类）
2. 数据清洗和验证
3. 向量化（使用moka-ai/m3e-base模型）
4. 批量插入到数据库
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import psycopg
from sentence_transformers import SentenceTransformer

from backend.infrastructure.database.vector_connection import get_vector_db_connection
from backend.infrastructure.database.models.rag_models import (
    QAExample,
    RecordExample,
    QueryExample,
    GreetingExample
)

# 配置日志
logger = logging.getLogger(__name__)

# Sheet名称到模型类的映射
SHEET_TO_MODEL = {
    "qa_examples": QAExample,
    "record_examples": RecordExample,
    "query_examples": QueryExample,
    "greeting_examples": GreetingExample,
}

# 模型类到表名的映射
MODEL_TO_TABLE = {
    QAExample: "qa_examples",
    RecordExample: "record_examples",
    QueryExample: "query_examples",
    GreetingExample: "greeting_examples",
}


class EmbeddingModelCache:
    """向量化模型缓存类（单例模式）"""
    
    _instance: Optional['EmbeddingModelCache'] = None
    _model: Optional[SentenceTransformer] = None
    _model_name: str = "moka-ai/m3e-base"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_model(self) -> SentenceTransformer:
        """
        获取向量化模型（懒加载，首次调用时加载）
        
        Returns:
            SentenceTransformer: 向量化模型实例
        """
        if self._model is None:
            logger.info(f"正在加载Embedding模型（{self._model_name}）...")
            
            # 检查模型是否已下载到本地缓存
            cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
            model_dir = cache_dir / f"models--{self._model_name.replace('/', '--')}"
            model_exists = model_dir.exists() and (model_dir / "snapshots").exists()
            
            if model_exists:
                logger.info("  ✓ 检测到本地模型缓存，将使用本地模型（无需下载，离线模式）")
                # 使用 local_files_only=True 避免网络请求
                self._model = SentenceTransformer(self._model_name, local_files_only=True)
            else:
                logger.info("  ⚠️  未检测到本地模型，将自动下载（首次运行，可能需要一些时间）")
                # 需要从网络下载，不使用 local_files_only
                self._model = SentenceTransformer(self._model_name)
            
            logger.info(f"✓ Embedding模型加载成功，模型维度: {self._model.get_sentence_embedding_dimension()}")
        
        return self._model
    
    def text_to_embedding(self, text: str) -> list:
        """
        将文本转换为768维向量
        
        Args:
            text: 输入文本
            
        Returns:
            list: 768维向量列表
        """
        model = self.get_model()
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()


class ExcelParser:
    """Excel文件解析器"""
    
    def __init__(self, excel_path: Path):
        """
        初始化Excel解析器
        
        Args:
            excel_path: Excel文件路径
        """
        self.excel_path = excel_path
        if not excel_path.exists():
            raise FileNotFoundError(f"Excel文件不存在: {excel_path}")
    
    def read_sheets(self) -> Dict[str, pd.DataFrame]:
        """
        读取Excel文件的所有Sheet
        
        Returns:
            Dict[str, pd.DataFrame]: Sheet名称到DataFrame的映射
        """
        logger.info(f"正在读取Excel文件: {self.excel_path}")
        
        try:
            # 读取所有Sheet
            excel_file = pd.ExcelFile(self.excel_path, engine='openpyxl')
            sheets = {}
            
            for sheet_name in excel_file.sheet_names:
                logger.info(f"  读取Sheet: {sheet_name}")
                df = pd.read_excel(excel_file, sheet_name=sheet_name, engine='openpyxl')
                sheets[sheet_name] = df
            
            logger.info(f"✓ 成功读取 {len(sheets)} 个Sheet")
            return sheets
        
        except Exception as e:
            logger.error(f"读取Excel文件失败: {e}")
            raise
    
    def parse_sheet(self, sheet_name: str, df: pd.DataFrame) -> List[Dict]:
        """
        解析单个Sheet的数据
        
        Args:
            sheet_name: Sheet名称
            df: DataFrame数据
            
        Returns:
            List[Dict]: 解析后的数据列表
        """
        logger.info(f"正在解析Sheet: {sheet_name}")
        
        # 检查Sheet名称是否有效
        if sheet_name not in SHEET_TO_MODEL:
            logger.warning(f"  跳过未知的Sheet: {sheet_name}（有效Sheet: {list(SHEET_TO_MODEL.keys())}）")
            return []
        
        # 必需的列
        required_columns = ['user_input', 'agent_response']
        optional_columns = ['tags', 'quality_grade']
        
        # 检查必需的列是否存在
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.error(f"  Sheet '{sheet_name}' 缺少必需的列: {missing_columns}")
            return []
        
        # 数据清洗和验证
        parsed_data = []
        for idx, row in df.iterrows():
            try:
                # 提取必需字段
                user_input = str(row['user_input']).strip()
                agent_response = str(row['agent_response']).strip()
                
                # 验证必需字段不为空
                if not user_input or not agent_response:
                    logger.warning(f"  第 {idx + 2} 行数据不完整（user_input或agent_response为空），跳过")
                    continue
                
                # 提取可选字段
                tags = None
                if 'tags' in df.columns and pd.notna(row.get('tags')):
                    tags_str = str(row['tags']).strip()
                    if tags_str:
                        # 将逗号分隔的字符串转换为列表
                        tags = [tag.strip() for tag in tags_str.split(',') if tag.strip()]
                
                quality_grade = None
                if 'quality_grade' in df.columns and pd.notna(row.get('quality_grade')):
                    quality_grade = str(row['quality_grade']).strip()
                    if not quality_grade:
                        quality_grade = None
                
                parsed_data.append({
                    'user_input': user_input,
                    'agent_response': agent_response,
                    'tags': tags,
                    'quality_grade': quality_grade,
                })
            
            except Exception as e:
                logger.warning(f"  第 {idx + 2} 行数据解析失败: {e}，跳过")
                continue
        
        logger.info(f"  ✓ Sheet '{sheet_name}' 解析完成，有效数据: {len(parsed_data)} 条")
        return parsed_data


class DataImporter:
    """数据导入器"""
    
    def __init__(self, conn: Optional[psycopg.Connection] = None):
        """
        初始化数据导入器
        
        Args:
            conn: 数据库连接（如果为None，会在需要时自动创建）
        """
        self.conn = conn
        self.embedding_cache = EmbeddingModelCache()
        self._should_close_conn = conn is None
    
    def build_embedding_text(self, user_input: str, agent_response: str) -> str:
        """
        构建用于向量化的文本（组合user_input和agent_response）
        
        Args:
            user_input: 用户输入
            agent_response: Agent回复
            
        Returns:
            str: 组合后的文本
        """
        return f"{user_input} {agent_response}"
    
    def insert_batch(
        self,
        model_class,
        table_name: str,
        data_list: List[Dict],
        batch_size: int = 100
    ) -> Tuple[int, int]:
        """
        批量插入数据到数据库
        
        Args:
            model_class: SQLAlchemy模型类
            table_name: 表名（用于日志）
            data_list: 数据列表
            batch_size: 批次大小
            
        Returns:
            Tuple[int, int]: (成功数量, 失败数量)
        """
        if not data_list:
            return 0, 0
        
        logger.info(f"正在导入数据到表: {table_name}，共 {len(data_list)} 条")
        
        success_count = 0
        fail_count = 0
        
        # 批量处理
        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(data_list) + batch_size - 1) // batch_size
            
            logger.info(f"  处理批次 {batch_num}/{total_batches}（{len(batch)} 条）...")
            
            batch_success = 0
            batch_fail = 0
            
            try:
                with self.conn.cursor() as cur:
                    for item in batch:
                        try:
                            # 构建向量化文本
                            embedding_text = self.build_embedding_text(
                                item['user_input'],
                                item['agent_response']
                            )
                            
                            # 生成向量
                            embedding_vector = self.embedding_cache.text_to_embedding(embedding_text)
                            
                            # 构建SQL插入语句
                            # 注意：这里使用原生SQL，因为pgvector的Vector类型在psycopg中需要特殊处理
                            sql = f"""
                                INSERT INTO gd2502_{table_name} 
                                (user_input, agent_response, tags, quality_grade, embedding)
                                VALUES (%s, %s, %s, %s, %s)
                            """
                            
                            cur.execute(sql, (
                                item['user_input'],
                                item['agent_response'],
                                item['tags'],
                                item['quality_grade'],
                                embedding_vector  # psycopg会自动转换为vector类型
                            ))
                            
                            batch_success += 1
                        
                        except Exception as e:
                            logger.warning(f"    插入数据失败: {e}")
                            batch_fail += 1
                            continue
                    
                    # 提交批次
                    self.conn.commit()
                    success_count += batch_success
                    fail_count += batch_fail
                    logger.info(f"  ✓ 批次 {batch_num} 完成（成功: {batch_success}, 失败: {batch_fail}）")
            
            except Exception as e:
                logger.error(f"  批次 {batch_num} 处理失败: {e}")
                self.conn.rollback()
                fail_count += len(batch)
        
        logger.info(f"✓ 表 {table_name} 导入完成（成功: {success_count}, 失败: {fail_count}）")
        return success_count, fail_count
    
    def import_from_excel(
        self,
        excel_path: Path,
        clear_existing: bool = False
    ) -> Dict[str, Dict[str, int]]:
        """
        从Excel文件导入数据
        
        Args:
            excel_path: Excel文件路径
            clear_existing: 是否清空现有数据
            
        Returns:
            Dict[str, Dict[str, int]]: 导入结果统计
        """
        # 如果没有提供连接，创建新连接
        if self.conn is None:
            self.conn = get_vector_db_connection()
        logger.info("=" * 60)
        logger.info("开始导入数据")
        logger.info("=" * 60)
        
        # 解析Excel文件
        parser = ExcelParser(excel_path)
        sheets = parser.read_sheets()
        
        # 如果清空现有数据
        if clear_existing:
            logger.info("正在清空现有数据...")
            with self.conn.cursor() as cur:
                for table_name in MODEL_TO_TABLE.values():
                    cur.execute(f"TRUNCATE TABLE gd2502_{table_name} RESTART IDENTITY")
                self.conn.commit()
            logger.info("✓ 现有数据已清空")
        
        # 导入结果统计
        import_results = {}
        
        # 遍历每个Sheet
        for sheet_name, df in sheets.items():
            # 解析Sheet数据
            parsed_data = parser.parse_sheet(sheet_name, df)
            
            if not parsed_data:
                logger.warning(f"Sheet '{sheet_name}' 没有有效数据，跳过")
                continue
            
            # 获取对应的模型类
            model_class = SHEET_TO_MODEL.get(sheet_name)
            if not model_class:
                logger.warning(f"Sheet '{sheet_name}' 没有对应的模型类，跳过")
                continue
            
            # 获取表名
            table_name = MODEL_TO_TABLE[model_class]
            
            # 批量插入
            success_count, fail_count = self.insert_batch(
                model_class,
                table_name,
                parsed_data
            )
            
            import_results[sheet_name] = {
                "success": success_count,
                "fail": fail_count
            }
        
        logger.info("=" * 60)
        logger.info("数据导入完成")
        logger.info("=" * 60)
        
        # 打印统计信息
        total_success = sum(r["success"] for r in import_results.values())
        total_fail = sum(r["fail"] for r in import_results.values())
        logger.info(f"总计：成功 {total_success} 条，失败 {total_fail} 条")
        
        # 如果连接是我们创建的，关闭它
        if self._should_close_conn and self.conn:
            self.conn.close()
            self.conn = None
        
        return import_results

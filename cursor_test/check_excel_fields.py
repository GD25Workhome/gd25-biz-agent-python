"""
临时脚本：检查 Excel 文件的字段
"""
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import pandas as pd
except ImportError:
    try:
        import openpyxl
        # 使用 openpyxl 读取
        def read_excel_columns(file_path):
            wb = openpyxl.load_workbook(file_path, read_only=True)
            ws = wb.active
            columns = [cell.value for cell in ws[1]]
            wb.close()
            return columns
    except ImportError:
        print("错误：需要安装 pandas 或 openpyxl")
        print("请运行: pip install pandas openpyxl")
        sys.exit(1)
        read_excel_columns = None

def check_excel_fields():
    """检查 Excel 文件的字段"""
    excel_files = [
        'static/rag_source/uat_data/4.1 lsk_副本.xlsx',
        'static/rag_source/uat_data/sh-1128_副本.xlsx'
    ]
    
    # 数据库模型字段（排除 id, created_at, updated_at 这些自动生成的字段）
    db_fields = {
        'age', 'disease', 'blood_pressure', 'symptom', 'medication', 
        'medication_status', 'habit', 'history_action', 'history_session', 
        'history_response', 'new_session', 'new_session_response', 
        'ids', 'ext', 'source_filename', 'source_remark1'
    }
    
    # 中英文字段映射关系（根据数据库模型的 comment 注释）
    field_mapping = {
        '年龄': 'age',
        '疾病': 'disease',
        '血压': 'blood_pressure',
        '症状': 'symptom',
        '用药': 'medication',
        '用药情况': 'medication_status',
        '习惯': 'habit',
        '历史Action': 'history_action',
        '历史会话': 'history_session',
        '历史会话响应': 'history_response',
        '新会话': 'new_session',
        '新会话响应': 'new_session_response',
        'ids': 'ids',
        'ext': 'ext',
        # 可能的变体映射
        '会话输入': 'new_session',  # 可能是新会话的另一种表述
        '供应商响应()': 'new_session_response',  # 可能是新会话响应的另一种表述
        'patient_id': 'ids',  # 可能是 ids 的另一种表述
    }
    
    all_excel_fields = {}
    all_missing_fields = set()
    
    for file_path in excel_files:
        if not os.path.exists(file_path):
            print(f"警告：文件不存在 - {file_path}")
            continue
            
        try:
            if 'pandas' in sys.modules:
                df = pd.read_excel(file_path, nrows=0)
                columns = list(df.columns)
            else:
                columns = read_excel_columns(file_path)
            
            # 清理列名（去除空格等）
            columns_clean = [str(col).strip() if col else '' for col in columns]
            all_excel_fields[os.path.basename(file_path)] = columns_clean
            
            print(f"\n{'='*60}")
            print(f"文件: {os.path.basename(file_path)}")
            print(f"{'='*60}")
            print(f"Excel 字段总数: {len(columns_clean)}")
            print(f"字段列表:")
            for i, col in enumerate(columns_clean, 1):
                print(f"  {i:2d}. {col}")
            
            # 找出不在数据库表中的字段
            missing_in_db = []
            matched_fields = []
            
            for col in columns_clean:
                if not col:  # 跳过空字段
                    missing_in_db.append(col)
                    continue
                    
                # 通过映射关系查找
                mapped_field = field_mapping.get(col)
                if mapped_field and mapped_field in db_fields:
                    matched_fields.append((col, mapped_field))
                    continue
                
                # 尝试直接匹配（忽略大小写和空格）
                col_lower = col.lower().replace(' ', '_').replace('-', '_').replace('()', '')
                found = False
                for db_field in db_fields:
                    if col_lower == db_field.lower() or col == db_field:
                        matched_fields.append((col, db_field))
                        found = True
                        break
                
                if not found:
                    missing_in_db.append(col)
                    all_missing_fields.add(col)
            
            if matched_fields:
                print(f"\n✅ 已匹配的字段 ({len(matched_fields)} 个):")
                for excel_field, db_field in matched_fields:
                    print(f"  - {excel_field} -> {db_field}")
            
            if missing_in_db:
                print(f"\n❌ 不在数据库表中的字段 ({len(missing_in_db)} 个):")
                for field in missing_in_db:
                    if field:  # 只显示非空字段
                        print(f"  - {field}")
                    else:
                        print(f"  - (空字段)")
            else:
                print(f"\n✅ 所有字段都在数据库表中")
                
        except Exception as e:
            print(f"错误：读取文件 {file_path} 时出错: {e}")
            import traceback
            traceback.print_exc()
    
    # 汇总对比
    print(f"\n{'='*60}")
    print("汇总对比")
    print(f"{'='*60}")
    print(f"\n数据库模型字段 ({len(db_fields)} 个):")
    for field in sorted(db_fields):
        print(f"  - {field}")
    
    # 找出所有 Excel 中独有的字段（排除空字段）
    truly_missing = [f for f in sorted(all_missing_fields) if f]
    
    if truly_missing:
        print(f"\n❌ Excel 中存在但数据库表中没有的字段 ({len(truly_missing)} 个):")
        for field in truly_missing:
            print(f"  - {field}")
        print(f"\n💡 建议：")
        print(f"  1. 如果这些字段需要保存，需要在数据库模型中添加对应字段")
        print(f"  2. 如果这些字段不需要保存，可以在数据清洗时忽略")
    else:
        print(f"\n✅ 所有 Excel 字段都能在数据库表中找到对应字段")

if __name__ == '__main__':
    check_excel_fields()

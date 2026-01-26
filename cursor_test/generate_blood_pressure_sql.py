#!/usr/bin/env python3
"""
生成血压历史数据的INSERT SQL语句
用于"晨间高-时段有不达标"场景测试
"""
from datetime import datetime, timedelta
from ulid import ULID

# 用户ID
USER_ID = "01KFWR3M8MAD3Y70D6HNR40HJR"

# 表名
TABLE_NAME = "gd2502_blood_pressure_records"

# 历史数据定义（7天，共13条记录）
# 格式: (天数前, 时间, 收缩压, 舒张压, 心率, 说明)
HISTORY_DATA = [
    # 第1天（7天前）
    (7, "08:00", 145, 85, 72, "晨间-不达标"),
    
    # 第2天（6天前）
    (6, "07:30", 142, 82, 70, "晨间-不达标"),
    (6, "15:00", 110, 68, 68, "下午-达标"),
    
    # 第3天（5天前）
    (5, "08:30", 143, 78, 71, "晨间-不达标"),
    (5, "20:00", 108, 66, 65, "夜间-达标"),
    
    # 第4天（4天前）
    (4, "07:00", 144, 83, 73, "晨间-不达标"),
    (4, "14:00", 112, 70, 69, "下午-达标"),
    
    # 第5天（3天前）
    (3, "09:00", 141, 79, 70, "晨间-不达标"),
    (3, "19:30", 114, 70, 67, "夜间-达标"),
    
    # 第6天（2天前）
    (2, "08:00", 145, 81, 72, "晨间-不达标"),
    (2, "16:00", 116, 71, 68, "下午-达标"),
    
    # 第7天（1天前）
    (1, "07:30", 142, 82, 71, "晨间-不达标"),
    (1, "21:00", 107, 65, 66, "夜间-达标"),
]

def generate_sql():
    """生成INSERT SQL语句"""
    now = datetime.now()
    sql_statements = []
    
    sql_statements.append("-- 血压历史数据插入SQL")
    sql_statements.append(f"-- 用户ID: {USER_ID}")
    sql_statements.append("-- 场景: 晨间高-时段有不达标")
    sql_statements.append("-- 目标值: 收缩压128mmHg, 舒张压80mmHg")
    sql_statements.append("--")
    sql_statements.append("-- 数据说明:")
    sql_statements.append("-- - 共13条记录，覆盖最近7天")
    sql_statements.append("-- - 晨间记录7条（2点-10点），平均收缩压约143.1mmHg")
    sql_statements.append("-- - 其他时段记录6条，平均收缩压约109.5mmHg")
    sql_statements.append("-- - 晨间平均收缩压高于全日平均收缩压约12%（满足>10%的要求）")
    sql_statements.append("-- - 所有晨间记录均不达标（收缩压>128或舒张压>80）")
    sql_statements.append("")
    
    for days_ago, time_str, systolic, diastolic, heart_rate, note in HISTORY_DATA:
        # 生成ULID
        record_id = str(ULID())
        
        # 计算记录时间
        record_date = now - timedelta(days=days_ago)
        hour, minute = map(int, time_str.split(":"))
        record_time = record_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        # 格式化时间戳为PostgreSQL格式
        record_time_str = record_time.strftime("%Y-%m-%d %H:%M:%S")
        created_at_str = record_date.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        
        # 生成INSERT语句
        sql = f"""INSERT INTO {TABLE_NAME} (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '{record_id}',
    '{USER_ID}',
    {systolic},  -- 收缩压 ({note})
    {diastolic},   -- 舒张压
    {heart_rate},   -- 心率
    TIMESTAMP '{record_time_str}',  -- 记录时间：{days_ago}天前 {time_str}
    TIMESTAMP '{created_at_str}',
    NULL
);"""
        
        sql_statements.append(sql)
        sql_statements.append("")
    
    # 添加验证注释
    sql_statements.append("-- 验证数据统计:")
    sql_statements.append("-- 晨间记录（2点-10点）: 7条")
    sql_statements.append("--   平均收缩压: (145+142+143+144+141+145+142)/7 ≈ 143.1 mmHg")
    sql_statements.append("--   所有晨间记录均不达标")
    sql_statements.append("-- 其他时段记录: 6条")
    sql_statements.append("--   平均收缩压: (110+108+112+114+116+107)/6 ≈ 109.5 mmHg")
    sql_statements.append("--   所有其他时段记录均达标")
    sql_statements.append("-- 全日平均收缩压: (1002+657)/13 ≈ 127.6 mmHg")
    sql_statements.append("-- 晨间平均/全日平均 = 143.1/127.6 ≈ 1.12 (高12%，满足>10%的要求)")
    
    return "\n".join(sql_statements)

if __name__ == "__main__":
    sql = generate_sql()
    print(sql)
    
    # 同时保存到文件
    output_file = "cursor_test/blood_pressure_insert.sql"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(sql)
    print(f"\n\nSQL已保存到: {output_file}")

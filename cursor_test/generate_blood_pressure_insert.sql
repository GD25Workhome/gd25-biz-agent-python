-- 血压历史数据插入SQL
-- 用户ID: 01KFWR3M8MAD3Y70D6HNR40HJR
-- 场景: 晨间高-时段有不达标
-- 目标值: 收缩压128mmHg, 舒张压80mmHg
-- 
-- 数据说明:
-- - 共13条记录，覆盖最近7天
-- - 晨间记录7条（2点-10点），平均收缩压约143.1mmHg
-- - 其他时段记录6条，平均收缩压约109.5mmHg
-- - 晨间平均收缩压高于全日平均收缩压约12%（满足>10%的要求）
-- - 所有晨间记录均不达标（收缩压>128或舒张压>80）

-- 第1天（7天前）
INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V0W',  -- ULID格式ID
    '01KFWR3M8MAD3Y70D6HNR40HJR',  -- 用户ID
    145,  -- 收缩压（不达标：145>128）
    85,   -- 舒张压（不达标：85>80）
    72,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '7 days')::timestamp + TIME '08:00:00',  -- 记录时间：7天前 08:00（晨间）
    CURRENT_TIMESTAMP - INTERVAL '7 days',
    NULL
);

-- 第2天（6天前）
INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V0X',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    142,  -- 收缩压（不达标：142>128）
    82,   -- 舒张压（不达标：82>80）
    70,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '6 days')::timestamp + TIME '07:30:00',  -- 记录时间：6天前 07:30（晨间）
    CURRENT_TIMESTAMP - INTERVAL '6 days',
    NULL
);

INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V0Y',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    110,  -- 收缩压（达标）
    68,   -- 舒张压（达标）
    68,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '6 days')::timestamp + TIME '15:00:00',  -- 记录时间：6天前 15:00（下午）
    CURRENT_TIMESTAMP - INTERVAL '6 days',
    NULL
);

-- 第3天（5天前）
INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V0Z',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    143,  -- 收缩压（不达标：143>128）
    78,   -- 舒张压（达标）
    71,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '5 days')::timestamp + TIME '08:30:00',  -- 记录时间：5天前 08:30（晨间）
    CURRENT_TIMESTAMP - INTERVAL '5 days',
    NULL
);

INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V1A',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    108,  -- 收缩压（达标）
    66,   -- 舒张压（达标）
    65,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '5 days')::timestamp + TIME '20:00:00',  -- 记录时间：5天前 20:00（夜间）
    CURRENT_TIMESTAMP - INTERVAL '5 days',
    NULL
);

-- 第4天（4天前）
INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V1B',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    144,  -- 收缩压（不达标：144>128）
    83,   -- 舒张压（不达标：83>80）
    73,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '4 days')::timestamp + TIME '07:00:00',  -- 记录时间：4天前 07:00（晨间）
    CURRENT_TIMESTAMP - INTERVAL '4 days',
    NULL
);

INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V1C',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    112,  -- 收缩压（达标）
    70,   -- 舒张压（达标）
    69,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '4 days')::timestamp + TIME '14:00:00',  -- 记录时间：4天前 14:00（下午）
    CURRENT_TIMESTAMP - INTERVAL '4 days',
    NULL
);

-- 第5天（3天前）
INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V1D',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    141,  -- 收缩压（不达标：141>128）
    79,   -- 舒张压（达标）
    70,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '3 days')::timestamp + TIME '09:00:00',  -- 记录时间：3天前 09:00（晨间）
    CURRENT_TIMESTAMP - INTERVAL '3 days',
    NULL
);

INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V1E',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    114,  -- 收缩压（达标）
    70,   -- 舒张压（达标）
    67,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '3 days')::timestamp + TIME '19:30:00',  -- 记录时间：3天前 19:30（夜间）
    CURRENT_TIMESTAMP - INTERVAL '3 days',
    NULL
);

-- 第6天（2天前）
INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V1F',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    145,  -- 收缩压（不达标：145>128）
    81,   -- 舒张压（不达标：81>80）
    72,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '2 days')::timestamp + TIME '08:00:00',  -- 记录时间：2天前 08:00（晨间）
    CURRENT_TIMESTAMP - INTERVAL '2 days',
    NULL
);

INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V1G',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    116,  -- 收缩压（达标）
    71,   -- 舒张压（达标）
    68,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '2 days')::timestamp + TIME '16:00:00',  -- 记录时间：2天前 16:00（下午）
    CURRENT_TIMESTAMP - INTERVAL '2 days',
    NULL
);

-- 第7天（1天前）
INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V1H',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    142,  -- 收缩压（不达标：142>128）
    82,   -- 舒张压（不达标：82>80）
    71,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '1 day')::timestamp + TIME '07:30:00',  -- 记录时间：1天前 07:30（晨间）
    CURRENT_TIMESTAMP - INTERVAL '1 day',
    NULL
);

INSERT INTO gd2502_blood_pressure_records (id, user_id, systolic, diastolic, heart_rate, record_time, created_at, updated_at)
VALUES (
    '01HZ8K9M2N3P4Q5R6S7T8U9V1I',
    '01KFWR3M8MAD3Y70D6HNR40HJR',
    107,  -- 收缩压（达标）
    65,   -- 舒张压（达标）
    66,   -- 心率
    (CURRENT_TIMESTAMP - INTERVAL '1 day')::timestamp + TIME '21:00:00',  -- 记录时间：1天前 21:00（夜间）
    CURRENT_TIMESTAMP - INTERVAL '1 day',
    NULL
);

-- 验证数据统计:
-- 晨间记录（2点-10点）: 7条
--   平均收缩压: (145+142+143+144+141+145+142)/7 ≈ 143.1 mmHg
--   所有晨间记录均不达标
-- 其他时段记录: 6条
--   平均收缩压: (110+108+112+114+116+107)/6 ≈ 109.5 mmHg
--   所有其他时段记录均达标
-- 全日平均收缩压: (1002+657)/13 ≈ 127.6 mmHg
-- 晨间平均/全日平均 = 143.1/127.6 ≈ 1.12 (高12%，满足>10%的要求)

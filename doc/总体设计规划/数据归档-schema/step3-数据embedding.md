# 目的
-  将step2的最终结构进行embedding

# 总体设计
- 使用批次模块调用embedding的模型生成数据，然后将数据存入系统
- 组成：
    1. 批次任务模块
    2. embedding模块

## 批次任务模块
- 负责将数据清洗模块的数据（pipeline_data_items_rewritten）新建批次，然后按照批次进行embedding
- 功能有：新建任务入口、执行任务界面、查询任务执行情况界面
- ER：
    1. 批次表：code、总数、查询参数
    2. 子任务表：来源表ID、来源表名、状态、运行时参数、冗余key、执行返回结果、执行失败信息、执行返回标识key

## embedding 模块


# embeding逻辑

- 目的将pipeline_data_items_rewritten的数据给embedding，然后存到新表中
- 当前mvp设计是只将数据清洗到表中，其它都暂时不处理

## 表设计（pipeline_embedding_records  Embedding记录）

- embedding_str 用于生成 embedding 的文本
- embedding_value Embedding向量值（2048维）
- embedding_type 类型：Q（只有提问）、QA（提问+回答）
- source_table_name 数据来源表名
- source_record_id 数据来源记录ID
- version 版本号（从0递增）
- is_published 是否发布
- trace_id Trace ID（可观测性追踪）
- generation_status 生成状态（0=进行中，1=成功，-1=失败）
- failure_reason 失败原因（含异常堆栈）

## 流程设计
- 原始数据读取
- 流程运行
- 。。。。
- 
- 前面有一个批次设计的代码，是否可以拿来复用呢？
  - [ ] 整理一下前面的流程的代码设计，考虑如何抄过来

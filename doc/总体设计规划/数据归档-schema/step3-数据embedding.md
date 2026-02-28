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
### 创建批次任务
- （模版类）创建流程
    1. 调用数据查询接口，返回task预创建对象（用于后续的实现）。需要子类实现
    2. 生成批次code。模版类默认实现，单也可以被子类定制化修改
    3. 组装batch_job、batch_task的数据库插入对象，生成数据。模版类实现
- 子类、业务实现类
    1. 继承模版类后，实现查询接口

### 批次任务执行
- （模版类）
    - 核心入参： BatchTaskRecord
    - 运行时：
        1. check task的状态是否为pending；然后尝试用乐观锁的方式更新状态为running。更新失败则打印error日志，并跳出任务执行
        2. 调用业务的实现方法执行，如果正常返回结果则任务执行成功，否则执行失败。并将结果记录到BatchTaskRecord中
            - 这里业务的实现方法应该是由模版类提供的模版方法
- embedding实现类
    - 核心入参：BatchTaskRecord的runtime_params，实际内容应该是pipeline_embedding_impl的runtime_params
    - 核心方法：对模版类的方法的实现。
        - 运行逻辑：
            1. 先根据pipeline_data_items_rewritten_id查询记录，
            2. 再根据embedding_type的类型拼接embedding的字符串，
            3. 然后调用embedding模型。这里的模型调用方式可以参考BeforeEmbeddingFuncNode._format_embedding_str中的逻辑。但是要区分embedding_type为Q和QA时的不同组装方案
            4. 调用成功后创建一条pipeline_embedding_records

## embedding 模块


# embeding逻辑

- 目的将pipeline_data_items_rewritten的数据给embedding，然后存到新表中
- 当前mvp设计是只将数据清洗到表中，其它都暂时不处理

## 表设计（pipeline_embedding_records  Embedding记录）

- embedding_str 用于生成 embedding 的文本
- embedding_value Embedding向量值（2048维）
- embedding_type 类型：Q（只有提问）、QA（提问+回答）
- is_published 是否发布
- type 主分类
- sub_type 子分类（不为空，如果子为空，业务上要拿主分类填充上）
- metadata 扩展元数据


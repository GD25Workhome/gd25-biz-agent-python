# 如何设计当前的数据提取流程？
- 如何融合，这套需要从数据库中去取值，故来源和之前的设计不一致了！
- 老的设计是使用langfuse进行管理，但是你实际用下来会发现langfuse其实使用起来没那么舒服，尤其是在进行数据查询时
- 真正的平台最好还是使用瀑布式进行数据管理，但是可以借助dataset的langfuse的形式，
## 融合方案-demo版本
1. 选择数据源
    1. 选择导入前是否清除老数据
    2. 预览新数据
    4. 确定导入
2. 选择导入的数据集，数据集目录、数据集版本（版本用日期进行管理）
3. 真正的平台，还是要采用

### 融合版本的数据结构
1. dataSets 数据集合
    - 关键字段：
        - 名称：string，200字符
        - path：路径，dataSetsPath的id
        - input schema：json
        - output schema：json
        - metadata：json
2. dataSetsItems 实际的数据
    - 关键字段：
        - unique_key:唯一key，可以不填，由业务来定义的唯一key，字段长度为200
        - input
        - output
        - metadata
        - status：1代表激活，0代表废弃
        - source：来源
3. dataSetsPath 数据集合的文件夹
    - 关键字段
        - id：这里的id可以主动设置
        - idPath：路径，上级的路径。比如根节点为空，下级节点的值为根节点的id，三级节点为一、二级节点的id拼接，使用英文逗号拼接
        - name：名称
        - description：描述
        - metadata：json格式
4. importConfig 导入配置
    - 关键字段
        - name
        - description
        - importConfig:json格式，根据实际的导入配置，选择导入的逻辑。由后台强绑定
### 前端界面设计
- 首先需要有个独立的节目入口，入口名字为“数据清洗”
- 界面中有多个菜单，同frontend下的index的风格。左侧是菜单，点击一个菜单，在中间新增一个tab页
- 第一个菜单为数据导入管理：可以选择各种导入的数据源，新建导入任务
- 第二个菜单为数据查看界面：可以管理dataSet的数据

## 数据导入的技术设计
- 首先要解决老的脚本如何导入数据的问题
- 核心实体为：
    - 数据读取方式，excel、数据库
    - excel的路径
    - excel的sheet name
    - 数据解析方式
- 这么说来大概需要哪些东西
    - 原属数据读取器（读取器excel和mysql各类型通用）
    - 数据初步清洗器（清洗器往往还会与excel的内容强绑定）
    - 清洗后数据入库器（这个通常是通用一套即可）
- 再说配置怎么处理，这里的配置的metadata决定了怎么读取，metadata的数据定义
    - 源的类型。excel,pg
    - 源的文件路径。json格式。如果是excel则为【"filePath":文件路径"】，如果是数据库则为【"tableName":"表A"】
    - sheetName。如果无，则excel全部
    - 数据清洗器。需要有默认清洗器，以及支持指定sheet的清洗器
        - 格式：sheetname -> 清洗器的key
        - 例子："default":"type1","sheet_name1":"typeA","sheet_name2":"typeB","sheet_name3":"typeC"
    - 入库执行器。不定义，采用全局通用，不用配置
- 导入最好还有一个导入的日志表，叫pipeline_log，字段有
    - 阶段：Step00数据导入、其它待定
    - 导入流程：这里可以是导入的py代码的类名缩写
    - metadata：json类型的导入元数据
    - status：1代表成功，0代表运行中，-1代表异常
    - logInfo：导入的过程信息，json类型，方便存储任何数据，通常会记录导入的时间消耗、数据统计情况、失败信息等

### 那么设计的思路为
1. 前端界面需要有一个入口
    - Step00导入管理界面，操作新增一个导入按钮
    - 后端有接口，接受导入配置id作为入参，查询配置表，得到配置的对象，进行后续导入的流程
2. 需要编写一个导入流程的专门的代码，来解析配置表的配置，然后进行数据导入工作


# 数据清洗的流程测试
## 导入
- 数据格式
    ```
        {
        "cleaners": {
            "default": "lsk",
            "常见问题及单轮": "sh1128_multi",
            "患者无数据+历史会话+历史Action": "sh1128_history_qa"
        },
        "dataSetsId": "01KGKT1RS0776XC90KCMGKG2J9",
        "sheetNames": [
            "常见问题及单轮",
            "患者无数据+历史会话+历史Action"
        ],
        "sourcePath": {
            "filePath": "static/rag_source/uat_data/sh-1128_副本.xlsx"
        },
        "sourceType": "excel",
        "clearBeforeImport": true
        }
    ```


# 来自安全边界的数据清洗
- 表：gd2502_knowledge_base
- 表的数据来自于产品prd的数据提取，借助流程create_rag_agent进行数据清洗后得到的数据
- 提取后表红的关键字段如下：
    1. scene_summary（场景摘要）：1～3 句自然语言，概括**该案例**的提问背景
    2. optimization_question（优化问题）：从原文的患者提问中总结出来，表达为完整、清晰、保留原意的问题；
    3. reply_example_or_rule（回复案例 or 规则）： 如果能直接提取出回复案例，则拿到回复案例；否则将规则提取出来，但是要在规则前加上“回复规则：”前缀
    4. scene_category（场景大类）：与原文「场景标识」中的「大类」严格一致
    5. input_tags（输入侧标签）：从 场景摘要 和 优化问题中提取
    6. response_tags（回复侧标签）：从回复案例中提取
    7. raw_material_full_text（原始资料-全量文字）：流程create_rag_agent的rag节点提取数据时用到的原属文本数据

## 如何整理成我的业务数据
- input
    - optimization_question 可以作为患者的发言
- output
    - reply_example_or_rule：可以作为回复或者回复的规则。
        - 如果是“回复规则：”开头，则需要将数据移动到回复规则中，这里就需要我的数据清洗时，设置规则兼容这种只有回复规则的schema了
- metadata
    - 新增original_extract字段的scene_summary字段，存储表中的scene_summary
    - 新增original_extract字段的scene_category字段，存储表中的scene_category
    - 新增original_extract字段的input_tags字段，存储表中的input_tags
    - 新增original_extract字段的response_tags字段，存储表中的response_tags
    - 新增original_extract字段的raw_material_full_text字段，存储表中的raw_material_full_text
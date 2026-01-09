# LangChain 工具管理机制详解

## 一、概述

在 LangChain 框架中，**工具（Tools）**是模型可以调用的函数，允许模型执行特定任务，如访问外部 API、查询数据库或执行计算。工具管理是 LangChain Agent 系统的核心组成部分。

## 二、工具的定义方式

LangChain 提供了两种主要方式来定义工具：

### 2.1 使用 `@tool` 装饰器（推荐方式）

这是最简单和推荐的方式，直接将 Python 函数转换为工具。

```python
from langchain_core.tools import tool

@tool
def record_blood_pressure(
    systolic: int,
    diastolic: int,
    heart_rate: int = None,
    notes: str = None
) -> str:
    """
    记录血压数据
    
    Args:
        systolic: 收缩压（mmHg）
        diastolic: 舒张压（mmHg）
        heart_rate: 心率（次/分钟，可选）
        notes: 备注（可选）
        
    Returns:
        记录结果的文本描述
    """
    # 实现逻辑
    return f"已记录血压数据：收缩压 {systolic} mmHg，舒张压 {diastolic} mmHg"
```

**关键点：**
- 函数的**文档字符串（docstring）**会被自动解析为工具描述
- **类型提示（type hints）**会被解析为工具的参数模式
- 装饰器会自动创建一个 `BaseTool` 实例

### 2.2 继承 `BaseTool` 类（高级方式）

当需要更精细的控制时，可以继承 `BaseTool` 类。

```python
from langchain_core.tools import BaseTool
from typing import Optional, Type
from pydantic import BaseModel, Field

class RecordBloodPressureInput(BaseModel):
    """记录血压的输入参数"""
    systolic: int = Field(description="收缩压（mmHg）")
    diastolic: int = Field(description="舒张压（mmHg）")
    heart_rate: Optional[int] = Field(None, description="心率（次/分钟）")
    notes: Optional[str] = Field(None, description="备注")

class RecordBloodPressureTool(BaseTool):
    """记录血压工具"""
    
    name: str = "record_blood_pressure"
    description: str = "记录用户的血压数据，包括收缩压、舒张压、心率和备注"
    args_schema: Type[BaseModel] = RecordBloodPressureInput
    
    def _run(
        self,
        systolic: int,
        diastolic: int,
        heart_rate: Optional[int] = None,
        notes: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """同步执行工具"""
        # 实现逻辑
        return f"已记录血压数据：收缩压 {systolic} mmHg"
    
    async def _arun(
        self,
        systolic: int,
        diastolic: int,
        heart_rate: Optional[int] = None,
        notes: Optional[str] = None,
        **kwargs: Any
    ) -> str:
        """异步执行工具"""
        # 实现逻辑
        return f"已记录血压数据：收缩压 {systolic} mmHg"
```

**关键点：**
- 必须实现 `_run`（同步）和 `_arun`（异步）方法
- 使用 `args_schema` 定义参数结构（Pydantic 模型）
- 可以完全控制工具的行为和元数据

## 三、工具的核心接口

### 3.1 BaseTool 的核心方法

所有工具都继承自 `BaseTool`，提供以下核心接口：

```python
class BaseTool:
    """工具基类"""
    
    name: str  # 工具名称
    description: str  # 工具描述
    args_schema: Optional[Type[BaseModel]]  # 参数模式
    
    def invoke(
        self,
        input: Union[str, Dict[str, Any]],
        config: Optional[RunnableConfig] = None,
        **kwargs: Any
    ) -> Any:
        """同步调用工具"""
        pass
    
    async def ainvoke(
        self,
        input: Union[str, Dict[str, Any]],
        config: Optional[RunnableConfig] = None,
        **kwargs: Any
    ) -> Any:
        """异步调用工具"""
        pass
    
    def _run(
        self,
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """同步执行（子类实现）"""
        raise NotImplementedError
    
    async def _arun(
        self,
        *args: Any,
        **kwargs: Any
    ) -> Any:
        """异步执行（子类实现）"""
        raise NotImplementedError
```

### 3.2 工具调用流程

```
用户输入 → Agent 决策 → 选择工具 → 调用 invoke/ainvoke
    ↓
解析参数 → 调用 _run/_arun → 执行逻辑 → 返回结果
    ↓
Agent 接收结果 → 生成回复 → 返回给用户
```

## 四、工具的管理方式

### 4.1 工具列表管理（标准方式）

LangChain 的标准做法是将工具作为列表传递给 Agent：

```python
from langchain.agents import create_react_agent
from langchain_core.prompts import ChatPromptTemplate

# 定义工具列表
tools = [
    record_blood_pressure,
    query_blood_pressure,
    update_blood_pressure
]

# 创建 Agent
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=system_prompt
)
```

**特点：**
- 简单直接，适合工具数量较少的情况
- Agent 可以访问所有工具
- 工具选择由 LLM 根据描述决定

### 4.2 工具注册表管理（项目实现方式）

当工具数量较多时，可以使用注册表模式：

```python
# 工具注册表（单例模式）
class ToolRegistry:
    """工具注册表"""
    
    _instance: 'ToolRegistry' = None
    _tools: Dict[str, BaseTool] = {}
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)
    
    def get_all_tools(self) -> Dict[str, BaseTool]:
        """获取所有工具"""
        return self._tools.copy()

# 全局注册表实例
tool_registry = ToolRegistry()

# 注册工具
tool_registry.register(record_blood_pressure)
tool_registry.register(query_blood_pressure)

# 从注册表获取工具
tools = [
    tool_registry.get_tool("record_blood_pressure"),
    tool_registry.get_tool("query_blood_pressure")
]
```

**优势：**
- 集中管理所有工具
- 支持按需加载工具
- 便于工具的动态发现和管理
- 支持工具的生命周期管理

### 4.3 动态工具选择（高级方式）

对于大量工具，可以使用语义搜索动态选择相关工具：

```python
from langchain.tools import Tool
from langchain.vectorstores import FAISS
from langchain.embeddings import OpenAIEmbeddings

# 1. 为所有工具创建描述索引
tool_descriptions = [
    {"name": tool.name, "description": tool.description}
    for tool in all_tools
]

# 2. 创建向量存储
embeddings = OpenAIEmbeddings()
vectorstore = FAISS.from_texts(
    [tool["description"] for tool in tool_descriptions],
    embeddings
)

# 3. 根据用户输入检索相关工具
def get_relevant_tools(user_input: str, k: int = 5):
    """根据用户输入检索相关工具"""
    results = vectorstore.similarity_search(user_input, k=k)
    tool_names = [result.page_content for result in results]
    return [tool_registry.get_tool(name) for name in tool_names]

# 4. 动态创建 Agent
user_input = "我想记录血压"
relevant_tools = get_relevant_tools(user_input)
agent = create_react_agent(model=llm, tools=relevant_tools)
```

**优势：**
- 减少 Agent 需要处理的工具数量
- 提高工具选择的准确性
- 降低 LLM 的计算开销

## 五、工具包装与增强

### 5.1 工具包装器模式

可以创建工具包装器来增强工具功能，例如自动注入上下文信息：

```python
class TokenInjectedTool(BaseTool):
    """
    工具包装器：在工具调用时自动注入 tokenId
    """
    
    def __init__(
        self,
        tool: BaseTool,
        token_id_param_name: str = "token_id",
        require_token: bool = True
    ):
        super().__init__(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
        )
        self._original_tool = tool
        self._token_id_param_name = token_id_param_name
        self._require_token = require_token
    
    def invoke(
        self,
        tool_input: Any,
        **kwargs: Any
    ) -> Any:
        """同步调用工具（自动注入 tokenId）"""
        if isinstance(tool_input, dict):
            # 从上下文获取 tokenId
            token_id = get_token_id()
            # 注入到参数中
            tool_input[self._token_id_param_name] = token_id
            return self._original_tool.invoke(tool_input, **kwargs)
        return self._original_tool.invoke(tool_input, **kwargs)
    
    async def ainvoke(
        self,
        tool_input: Any,
        **kwargs: Any
    ) -> Any:
        """异步调用工具（自动注入 tokenId）"""
        if isinstance(tool_input, dict):
            token_id = get_token_id()
            tool_input[self._token_id_param_name] = token_id
            return await self._original_tool.ainvoke(tool_input, **kwargs)
        return await self._original_tool.ainvoke(tool_input, **kwargs)
```

**使用场景：**
- 自动注入用户上下文（如 tokenId、用户ID）
- 添加日志记录
- 添加错误处理和重试机制
- 添加权限检查

### 5.2 批量包装工具

```python
def wrap_tools_with_token_context(
    tools: list[BaseTool],
    token_id_param_name: str = "token_id",
    require_token: bool = True
) -> list[BaseTool]:
    """批量包装工具，使其支持自动注入 tokenId"""
    wrapped_tools = []
    for tool in tools:
        if isinstance(tool, TokenInjectedTool):
            wrapped_tools.append(tool)
        else:
            wrapped_tool = TokenInjectedTool(
                tool=tool,
                token_id_param_name=token_id_param_name,
                require_token=require_token
            )
            wrapped_tools.append(wrapped_tool)
    return wrapped_tools

# 使用
tools = [record_blood_pressure, query_blood_pressure]
wrapped_tools = wrap_tools_with_token_context(tools)
```

## 六、工具与 Agent 的集成

### 6.1 在 Agent 中使用工具

```python
from langchain.agents import create_react_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# 1. 准备工具列表
tools = [
    record_blood_pressure,
    query_blood_pressure,
    update_blood_pressure
]

# 2. 创建系统提示词
system_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个专业的血压记录助手..."),
    MessagesPlaceholder(variable_name="messages"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# 3. 创建 ReAct Agent
agent = create_react_agent(
    model=llm,
    tools=tools,
    prompt=system_prompt
)

# 4. 调用 Agent
response = agent.invoke({
    "messages": [HumanMessage(content="我想记录血压，120/80")]
})
```

### 6.2 Agent 如何选择工具

Agent 使用 **ReAct 模式**（Reasoning + Acting）来选择工具：

1. **推理（Reasoning）**：LLM 分析用户输入，决定需要调用哪个工具
2. **行动（Acting）**：调用选定的工具
3. **观察（Observation）**：接收工具执行结果
4. **反思（Reflection）**：根据结果决定下一步行动

```
用户："我想记录血压，120/80"
    ↓
Agent 推理：需要调用 record_blood_pressure 工具
    ↓
Agent 行动：调用 record_blood_pressure(systolic=120, diastolic=80)
    ↓
工具执行：返回 "已记录血压数据：收缩压 120 mmHg，舒张压 80 mmHg"
    ↓
Agent 观察：收到工具执行结果
    ↓
Agent 回复："已成功记录您的血压数据：120/80"
```

## 七、项目中的工具管理实现

### 7.1 工具定义

项目使用 `@tool` 装饰器定义工具：

```13:66:backend/domain/tools/blood_pressure.py
@tool
def record_blood_pressure(
    systolic: int,
    diastolic: int,
    heart_rate: int = None,
    notes: str = None,
    token_id: str = ""  # 由TokenInjectedTool自动注入
) -> str:
    """
    记录血压数据
    
    Args:
        systolic: 收缩压（mmHg）
        diastolic: 舒张压（mmHg）
        heart_rate: 心率（次/分钟，可选）
        notes: 备注（可选）
        token_id: 用户ID（由系统自动注入，无需手动传递）
        
    Returns:
        记录结果的文本描述
    """
    # ... 实现逻辑 ...
```

### 7.2 工具注册表

项目实现了单例模式的工具注册表：

```12:63:backend/domain/tools/registry.py
class ToolRegistry:
    """工具注册表（单例模式）"""
    
    _instance: 'ToolRegistry' = None
    _tools: Dict[str, BaseTool] = {}
    
    def __new__(cls):
        """单例模式实现"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, tool: BaseTool) -> None:
        """
        注册工具
        
        Args:
            tool: 工具实例
        """
        self._tools[tool.name] = tool
        logger.info(f"注册工具: {tool.name}")
    
    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        获取工具
        
        Args:
            name: 工具名称
            
        Returns:
            工具实例，如果不存在则返回None
        """
        return self._tools.get(name)
    
    def get_all_tools(self) -> Dict[str, BaseTool]:
        """
        获取所有工具
        
        Returns:
            所有工具的字典
        """
        return self._tools.copy()
    
    def clear(self) -> None:
        """清空所有工具"""
        self._tools.clear()


# 创建全局工具注册表实例
tool_registry = ToolRegistry()
```

### 7.3 工具包装器

项目实现了 `TokenInjectedTool` 来自动注入用户上下文：

```15:223:backend/domain/tools/wrapper.py
class TokenInjectedTool(BaseTool):
    """
    工具包装器：在工具调用时自动注入 tokenId
    
    工作原理：
    1. 包装原始工具，保持所有属性和行为
    2. 在 invoke/ainvoke 时，从上下文获取 tokenId
    3. 自动将 tokenId 注入到工具参数中
    4. 调用原始工具函数
    """
    
    def __init__(
        self,
        tool: BaseTool,
        token_id_param_name: str = "token_id",
        require_token: bool = True
    ):
        """
        初始化工具包装器
        
        Args:
            tool: 原始工具实例
            token_id_param_name: tokenId 参数名称（默认为 "token_id"）
            require_token: 是否要求 tokenId 必须存在（默认 True）
        """
        # 先调用 super().__init__，然后再设置属性，确保属性不会被覆盖
        super().__init__(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
        )
        
        # 在 super().__init__ 之后设置属性，确保它们不会被覆盖
        self._original_tool = tool
        self._token_id_param_name = token_id_param_name
        self._require_token = require_token
    
    # ... invoke 和 ainvoke 方法实现 ...
```

## 八、总结

### 8.1 LangChain 工具管理的核心特点

1. **标准化接口**：所有工具都继承自 `BaseTool`，提供统一的调用接口
2. **灵活定义**：支持 `@tool` 装饰器和继承 `BaseTool` 两种方式
3. **自动解析**：从函数签名和文档字符串自动生成工具描述
4. **动态选择**：Agent 可以根据上下文动态选择工具
5. **易于扩展**：支持工具包装和增强

### 8.2 最佳实践

1. **使用 `@tool` 装饰器**：对于简单工具，优先使用装饰器方式
2. **详细的文档字符串**：提供清晰的工具描述和参数说明
3. **类型提示**：使用类型提示帮助 LLM 理解参数类型
4. **工具注册表**：对于大量工具，使用注册表集中管理
5. **工具包装**：使用包装器添加横切关注点（日志、权限、上下文注入等）

### 8.3 项目实现亮点

1. **单例注册表**：集中管理所有工具，便于维护
2. **上下文注入**：通过 `TokenInjectedTool` 自动注入用户上下文
3. **批量包装**：支持批量包装工具，提高开发效率
4. **配置驱动**：通过 YAML 配置管理 Agent 和工具的关系

---

**参考资源：**
- [LangChain Tools 官方文档](https://python.langchain.com/docs/modules/tools/)
- [LangChain BaseTool 源码](https://github.com/langchain-ai/langchain/blob/main/libs/langchain-core/langchain_core/tools.py)


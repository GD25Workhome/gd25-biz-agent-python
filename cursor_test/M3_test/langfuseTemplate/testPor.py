from langfuse import Langfuse

# 初始化 Langfuse 客户端
langfuse = Langfuse(
    public_key="pk-lf-47a6275e-64a5-4bdd-81de-c57c7decaa03",
    secret_key="sk-lf-e6404ef0-2947-4f6e-bb8d-1a4da3578ef9",
    host="https://us.cloud.langfuse.com"  # 或你的自托管地址
)

# LANGFUSE_SECRET_KEY = "sk-lf-e6404ef0-2947-4f6e-bb8d-1a4da3578ef9"
# LANGFUSE_PUBLIC_KEY = "pk-lf-47a6275e-64a5-4bdd-81de-c57c7decaa03"
# LANGFUSE_BASE_URL = "https://us.cloud.langfuse.com"

# 获取指定名称和版本（可选）的 Prompt
prompt = langfuse.get_prompt(
    name="blood_pressure_agent_prompt",        # 在 Langfuse 中定义的 prompt 名称
    version=1                # 可选：指定版本号；不传则默认获取最新版本
)

# # 渲染 Prompt（如果包含变量）
# rendered_prompt = prompt.compile(
#     topic="AI伦理",          # 假设你的 prompt 模板中有 {{topic}} 占位符
#     tone="正式"
# )

print("原始模板:", prompt.prompt)
# print("渲染后内容:", rendered_prompt)
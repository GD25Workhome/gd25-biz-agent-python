from fastapi import FastAPI
from app.api.routes import router
from app.core.config import settings

# 创建 FastAPI 应用实例
app = FastAPI(title="GD25 Biz Agent")

# 包含 API 路由
# prefix="/api/v1" 表示所有路由都以 /api/v1 开头
app.include_router(router, prefix="/api/v1")

@app.get("/health")
def health_check():
    """
    健康检查接口
    返回服务的状态和版本信息
    """
    return {"status": "ok", "version": "0.1.0"}

if __name__ == "__main__":
    import uvicorn
    # 启动应用服务器，监听 0.0.0.0:8000
    uvicorn.run(app, host="0.0.0.0", port=8000)

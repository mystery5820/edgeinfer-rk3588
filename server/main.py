from __future__ import annotations

from fastapi import FastAPI

from server.api.health_api import router as health_router
from server.api.model_api import router as model_router
from server.api.metrics_api import router as metrics_router
from server.api.chat_api import router as chat_router
from server.api.vision_api import router as vision_router
from server.api.infer_api import router as infer_router
from server.runtime.rkllm_backend import RKLLMBackend

app = FastAPI(
    title="EdgeInfer-RK3588 Serving Framework",
    version="phase9-mvp",
    description="端侧多模型推理服务框架 MVP：模型注册、健康检查、基础指标、LLM Chat API 原型。",
)

app.include_router(health_router)
app.include_router(model_router)
app.include_router(metrics_router)
app.include_router(chat_router)
app.include_router(vision_router)
app.include_router(infer_router)



@app.on_event("shutdown")
def shutdown_runtime():
    RKLLMBackend.stop_worker_runtime()


@app.get("/")
def root():
    return {
        "service": "edgeinfer-rk3588-serving",
        "version": "phase9-mvp",
        "docs": "/docs",
        "health": "/v1/health",
        "models": "/v1/models",
        "metrics": "/v1/metrics",
        "chat": "/v1/chat/completions",
        "vision_detect": "/v1/vision/detect",
        "infer": "/v1/infer",
        "infer_tasks": "/v1/infer/tasks",
    }

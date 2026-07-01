from __future__ import annotations

from fastapi import APIRouter, HTTPException

from server.model_manager.registry import ModelRegistry

router = APIRouter(prefix="/v1", tags=["models"])


@router.get("/models")
def list_models():
    registry = ModelRegistry()
    models = registry.list_models()

    validation = {}
    for model in models:
        validation[model["id"]] = registry.validate_model_entry(model)

    return {
        "count": len(models),
        "models": models,
        "validation": validation,
    }


@router.get("/models/{model_id}")
def get_model(model_id: str):
    registry = ModelRegistry()
    try:
        model = registry.get_model(model_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    errors = registry.validate_model_entry(model)
    return {
        "model": model,
        "validation_errors": errors,
    }

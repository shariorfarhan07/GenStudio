from fastapi import APIRouter
from app.pipelines.registry import pipeline_registry

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


@router.get("")
async def list_pipelines():
    return pipeline_registry.get_all()

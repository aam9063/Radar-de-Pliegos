from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.licitaciones import router as licitaciones_router
from app.api.perfil import router as perfil_router


def create_app() -> FastAPI:
    app = FastAPI(title="Radar de Pliegos API", version="0.1.0")
    app.include_router(health_router)
    app.include_router(licitaciones_router)
    app.include_router(perfil_router)
    return app


app = create_app()

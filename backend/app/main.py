from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.documentos import router as documentos_router
from app.api.health import router as health_router
from app.api.licitaciones import router as licitaciones_router
from app.api.perfil import router as perfil_router
from app.api.planificacion import router as planificacion_router

# Origins of the Vite dev server and preview builds that call this API.
FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def create_app() -> FastAPI:
    app = FastAPI(title="Radar de Pliegos API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=FRONTEND_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(licitaciones_router)
    app.include_router(documentos_router)
    app.include_router(perfil_router)
    app.include_router(planificacion_router)
    return app


app = create_app()

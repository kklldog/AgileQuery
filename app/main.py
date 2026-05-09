from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.admin import router as admin_router
from app.api.routes.health import router as health_router
from app.api.routes.query import router as query_router


def create_app() -> FastAPI:
    app = FastAPI(title="AgileQuery Backend MVP", version="0.1.0")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.include_router(health_router)
    app.include_router(query_router)
    app.include_router(admin_router)
    return app


app = create_app()

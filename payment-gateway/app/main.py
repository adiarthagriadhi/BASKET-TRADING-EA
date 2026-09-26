from fastapi import FastAPI

from .db import Base, engine
from .routers import admin, checkout, merchant, sandbox


def create_app() -> FastAPI:
    app = FastAPI(
        title="Payment Gateway",
        version="0.1.0",
        description="Platform payment gateway: merchant, pembayaran QRIS/VA/e-wallet, refund, webhook, saldo.",
    )
    app.include_router(admin.router)
    app.include_router(merchant.router)
    app.include_router(sandbox.router)
    app.include_router(checkout.router)

    @app.get("/health", tags=["system"])
    def health():
        return {"status": "ok"}

    return app


Base.metadata.create_all(engine)
app = create_app()

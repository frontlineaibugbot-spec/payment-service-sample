from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import init_db
from app.routers import accounts, exchange, health, payments, refunds, tax, transactions


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="payment-service-sample", lifespan=lifespan)

app.include_router(health.router)
app.include_router(payments.router)
app.include_router(refunds.router)
app.include_router(transactions.router)
app.include_router(exchange.router)
app.include_router(tax.router)
app.include_router(accounts.router)

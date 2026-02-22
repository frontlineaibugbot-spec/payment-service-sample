from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import accounts, exchange, health, payments, refunds, tax, transactions
from app.routers import checkout, batch_refund, international


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="payment-service-sample", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(payments.router)
app.include_router(refunds.router)
app.include_router(transactions.router)
app.include_router(exchange.router)
app.include_router(tax.router)
app.include_router(accounts.router)
app.include_router(checkout.router)
app.include_router(batch_refund.router)
app.include_router(international.router)

import os

from dotenv import load_dotenv

load_dotenv()

LOKI_PUSH_URL = os.getenv("LOKI_PUSH_URL", "http://localhost:3100/loki/api/v1/push")
SERVICE = "payment-service-sample"
ENV = os.getenv("ENV", "local")
FIXED_FEE = 2.50  # processing fee in dollars

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/payments",
)

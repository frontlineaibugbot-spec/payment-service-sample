from app.config import FIXED_FEE


def calculate_payment_fee(amount: float) -> float:
    """Calculate the processing fee.

    BUG: Raises ZeroDivisionError when amount=0.
    Fix: guard with `if amount <= 0: return FIXED_FEE`
    """
    fee = FIXED_FEE / amount  # ZeroDivisionError when amount == 0
    return round(fee, 4)

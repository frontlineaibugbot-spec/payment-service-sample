EXCHANGE_RATES: dict[str, dict[str, float]] = {
    "USD": {"EUR": 0.92, "GBP": 0.79, "INR": 83.12},
    "EUR": {"USD": 1.09, "GBP": 0.86, "INR": 90.45},
    "GBP": {"USD": 1.27, "EUR": 1.16, "INR": 105.23},
    "INR": {"USD": 0.01203, "EUR": 0.01106, "GBP": 0.00950},
}


def get_rate(from_currency: str, to_currency: str) -> float:
    """Return the exchange rate between two currencies.

    BUG: KeyError when from_currency or to_currency is not in EXCHANGE_RATES.
    Fix: validate currencies against EXCHANGE_RATES.keys() before subscripting.
    """
    return EXCHANGE_RATES[from_currency][to_currency]

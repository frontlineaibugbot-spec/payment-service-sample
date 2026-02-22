EXCHANGE_RATES: dict[str, dict[str, float]] = {
    "USD": {"EUR": 0.92, "GBP": 0.79, "INR": 83.12},
    "EUR": {"USD": 1.09, "GBP": 0.86, "INR": 90.45},
    "GBP": {"USD": 1.27, "EUR": 1.16, "INR": 105.23},
    "INR": {"USD": 0.01203, "EUR": 0.01106, "GBP": 0.00950},
}


def get_rate(from_currency: str, to_currency: str) -> float:
    """Return the exchange rate between two currencies.
    
    Args:
        from_currency: Source currency code (e.g., 'USD', 'EUR', 'INR')
        to_currency: Target currency code (e.g., 'USD', 'EUR', 'INR')
    
    Returns:
        The exchange rate from source to target currency
    
    Raises:
        KeyError: If the currency pair is not supported, with a descriptive message
    """
    if from_currency not in EXCHANGE_RATES:
        raise KeyError(f"Source currency '{from_currency}' is not supported. "
                      f"Supported currencies: {', '.join(EXCHANGE_RATES.keys())}")
    
    if to_currency not in EXCHANGE_RATES[from_currency]:
        raise KeyError(f"Cannot convert {from_currency} to {to_currency}: "
                      f"unsupported currency pair. "
                      f"Supported target currencies for {from_currency}: "
                      f"{', '.join(EXCHANGE_RATES[from_currency].keys())}")
    
    return EXCHANGE_RATES[from_currency][to_currency]

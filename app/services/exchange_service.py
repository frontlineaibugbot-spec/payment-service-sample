# DO NOT EDIT: Exchange rates are static and must not be modified.
from types import MappingProxyType

EXCHANGE_RATES: MappingProxyType = MappingProxyType({
    "USD": MappingProxyType({"EUR": 0.92, "GBP": 0.79, "INR": 83.12}),
    "EUR": MappingProxyType({"USD": 1.09, "GBP": 0.86, "INR": 90.45}),
    "GBP": MappingProxyType({"USD": 1.27, "EUR": 1.16, "INR": 105.23}),
})


def get_rate(from_currency: str, to_currency: str) -> float:
    """Return the exchange rate between two currencies.

    Raises:
        KeyError: If from_currency or to_currency is not supported.
    """
    if from_currency not in EXCHANGE_RATES:
        raise KeyError(f"Source currency '{from_currency}' is not supported")
    
    if to_currency not in EXCHANGE_RATES[from_currency]:
        raise KeyError(f"Target currency '{to_currency}' is not supported for source currency '{from_currency}'")
    
    return EXCHANGE_RATES[from_currency][to_currency]

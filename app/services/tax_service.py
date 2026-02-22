TAX_RATES: dict[str, dict[str, float]] = {
    "US": {"standard": 0.08, "reduced": 0.04},
    "GB": {"standard": 0.20, "reduced": 0.05},
    "DE": {"standard": 0.19, "reduced": 0.07},
}


def get_tax_rate(country_code: str, tax_type: str) -> float:
    """Return the tax rate for a given country and tax type.

    BUG: TypeError raised when country_code is not in TAX_RATES.
         TAX_RATES.get() returns None → None[tax_type] raises TypeError.
    Fix: check that country_rates is not None before subscripting.
    """
    country_rates = TAX_RATES.get(country_code)  # None for unknown country
    return country_rates[tax_type]               # TypeError: NoneType not subscriptable

"""Deliberately buggy webinar exercise; do not use as a billing library."""


def invoice_total(items):
    """Return integer cents for (price_cents, quantity) pairs, both nonnegative integers."""
    return sum(price for price, quantity in items)  # Exercise: quantity and validation missing.

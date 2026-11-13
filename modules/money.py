"""Money as a person reads it: the one formatter every amount on a screen goes through (the
operator, 2026-11-13: "money shown as $"). An amount is US dollars, written "$0.25": the sign
first, always with cents, thousands grouped, never "0.25 USD", "USD 0.25" or a bare number.

Two precisions, one function (`usd`), because a figure and a cost are read differently:

- **a figure** (the default: a total, a cap, an average, an estimate) is to the cent, "$0.65",
  "$2,400.00"; one that is not nothing and under a cent keeps four places ("$0.0011"), so
  spend never reads as "$0.00";
- **an exact amount** (``exact``: one call's cost, a rate, a sum a cap is compared with) is to
  the cent when it is a whole number of cents ("$1.00", "$0.25") and to four places when it is
  not ("$0.1251", "$0.0003"), so two amounts side by side read alike and a cost below a cent
  is still said.

Templates reach it as the `usd` filter (routes/v2.py); Python that builds a screen's words
calls it. What it is not: a parser (a typed amount is `installation_settings._value`'s), and
no caller passes it None: "no cap" and "unknown" are their callers' words.
"""


def usd(value, exact: bool = False) -> str:
    """*value* US dollars as "$1,234.50". *exact*: to four places when it is no whole number
    of cents. A negative amount (a difference) leads with its sign: "-$0.50"."""
    v = float(value)
    sign, v = ("-" if round(v, 4) < 0 else ""), abs(v)
    four = round(v, 4)
    cent_exact = round(four, 2) == four
    if (exact and not cent_exact) or (not exact and 0 < four < 0.01):
        return f"{sign}${four:,.4f}"
    return f"{sign}${round(v, 2):,.2f}"

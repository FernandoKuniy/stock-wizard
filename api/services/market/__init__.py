"""Market-data layer.

The only place in the codebase that talks to an external data provider (Finnhub
for quotes, profiles, and search; Twelve Data for candles). All external calls and
all caching live here so provider swaps and rate-limit handling stay in one spot.
"""

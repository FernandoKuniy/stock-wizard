"""Market-data layer.

The ONLY place in the codebase that talks to Finnhub. All external calls and all
caching live here so provider swaps and rate-limit handling stay in one spot.
"""

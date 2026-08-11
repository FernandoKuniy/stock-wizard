"""HTTP routers, one module per domain.

Each module exposes an ``APIRouter`` that ``main.py`` includes onto the app. Routes stay thin:
they pull code-computed figures from the analysis layer, run orders through the sim, and fetch
prices through the market layer, then hand back JSON. No financial figure is computed here
beyond rounding for display. Shared pieces (the dependency aliases and money rounding) live in
``routers.common``.
"""

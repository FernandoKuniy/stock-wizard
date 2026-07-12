"""Simulation layer: the paper-trading engine.

Pure-ish functions over the database session (cash, holdings, transactions), kept
free of HTTP and framework code so they are easy to unit test.
"""

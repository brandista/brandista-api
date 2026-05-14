"""Canonical platform auth — token primitives, FastAPI dependencies.

See docs/superpowers/specs/2026-05-14-canonical-auth-v2-design.md for the
contract. Coexists with legacy auth in main.py and app/dependencies.py;
they share SECRET_KEY but issue and accept different token shapes.
"""

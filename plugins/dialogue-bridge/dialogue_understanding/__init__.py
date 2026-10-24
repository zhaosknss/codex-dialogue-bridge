"""Portable, sourced understanding documents above an externally owned Ledger.

No host or model is invoked. The caller supplies validated original evidence;
this layer checks source identity/scope, retains attribution, and manages revisions.
"""

from .documents import DocumentStore

__all__ = ["DocumentStore"]

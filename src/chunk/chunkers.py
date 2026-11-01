"""P2 chunkers: each takes a frozen document plus its settings and returns character spans, before shared post-processing."""
from src.chunk.base import token_windows


def fixed_token(document, size, overlap=0):
    """P2-R02: windows of `size` bge-m3 tokens, cut at word starts."""
    return token_windows(document["text"], size, overlap)


CHUNKERS = {"fixed_token": {"function": fixed_token, "version": "1.0"}}
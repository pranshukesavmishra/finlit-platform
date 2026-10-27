"""Prism precompute workers side by side: every company goes to exactly one of them."""
from finlit.prism import in_shard

SYMBOLS = [f"SYM{i}" for i in range(500)] + ["M&M", "BAJAJ-AUTO", "ABB"]


def test_the_parts_are_disjoint_and_together_complete():
    for of in (1, 2, 3, 5):
        parts = [in_shard(SYMBOLS, (k, of)) for k in range(of)]
        flat = [s for p in parts for s in p]
        assert sorted(flat) == sorted(SYMBOLS) and len(flat) == len(set(flat))
    assert in_shard(SYMBOLS, None) == SYMBOLS


def test_the_split_is_stable_and_order_keeps_priority():
    a = in_shard(SYMBOLS, (0, 2))
    assert a == in_shard(SYMBOLS, (0, 2))
    assert a == [s for s in SYMBOLS if s in set(a)]       # the worker keeps the biggest-first order it was given

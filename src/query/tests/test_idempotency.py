"""Tests for idempotency cache."""

import uuid
from query.idempotency import IdempotencyCache


def test_cache_miss_returns_none():
    c = IdempotencyCache()
    assert c.get(uuid.uuid4(), uuid.uuid4()) is None


def test_cache_hit_returns_stored():
    c = IdempotencyCache()
    conv = uuid.uuid4()
    evt = uuid.uuid4()
    response = {"response_text": "Hello", "event_id": str(evt)}
    c.set(conv, evt, response)
    assert c.get(conv, evt) == response


def test_different_event_ids_independent():
    c = IdempotencyCache()
    conv = uuid.uuid4()
    evt1, evt2 = uuid.uuid4(), uuid.uuid4()
    c.set(conv, evt1, {"response_text": "A"})
    assert c.get(conv, evt2) is None


def test_clear_conversation():
    c = IdempotencyCache()
    conv = uuid.uuid4()
    evt = uuid.uuid4()
    c.set(conv, evt, {"response_text": "A"})
    c.clear_conversation(conv)
    assert c.get(conv, evt) is None

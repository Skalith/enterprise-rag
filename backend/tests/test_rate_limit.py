from app.utils.rate_limit import consume


def test_consume_allows_up_to_limit():
    key = f"unit:allow:{id(object())}"
    for _ in range(3):
        allowed, retry = consume(key, 3, window_seconds=60)
        assert allowed is True
        assert retry == 0


def test_consume_blocks_over_limit():
    key = f"unit:block:{id(object())}"
    for _ in range(2):
        assert consume(key, 2, window_seconds=60)[0] is True
    allowed, retry_after = consume(key, 2, window_seconds=60)
    assert allowed is False
    assert retry_after >= 1


def test_consume_zero_limit_disables():
    assert consume(f"unit:off:{id(object())}", 0, window_seconds=60) == (True, 0)

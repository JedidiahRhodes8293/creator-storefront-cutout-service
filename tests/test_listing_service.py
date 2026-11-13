from src.listing_service import should_publish


def test_cutout_publishes_only_when_subscribers_exist():
    assert should_publish(True, 3) is True
    assert should_publish(True, 0) is False
    assert should_publish(False, 3) is False

from investing_bot.stream_manager import StreamSubscriptionManager


def test_stream_manager_reconcile_subscribe_unsubscribe():
    manager = StreamSubscriptionManager()
    manager.set_desired("options", ["SPY", "QQQ"])
    first = manager.reconcile("options")
    assert len(first) == 1
    assert first[0].action == "subscribe"
    assert first[0].symbols == ("QQQ", "SPY")

    manager.set_desired("options", ["SPY", "IWM"])
    second = manager.reconcile("options")
    assert len(second) == 2
    assert second[0].action == "unsubscribe"
    assert second[0].symbols == ("QQQ",)
    assert second[1].action == "subscribe"
    assert second[1].symbols == ("IWM",)


def test_stream_manager_is_idempotent_after_reconcile():
    manager = StreamSubscriptionManager()
    manager.set_desired("options", ["SPY"])
    _ = manager.reconcile("options")
    again = manager.reconcile("options")
    assert again == []

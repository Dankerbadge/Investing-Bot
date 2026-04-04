import json

from investing_bot.archive import ArchiveWriter


def test_archive_writer_appends_jsonl(tmp_path):
    writer = ArchiveWriter(root_dir=tmp_path)
    path = writer.record_signal({"ticker": "SPY-TEST", "net_edge": 0.0123, "quote_age_seconds": 0.7})

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["ticker"] == "SPY-TEST"
    assert payload["data_source"] == "live"
    assert payload["quote_quality_tier"] == "realtime"
    assert payload["quote_reliability_score"] == 1.0
    assert payload["book_reliability_score"] > 0.0
    assert "recorded_at" in payload


def test_archive_writer_separates_live_and_ghost_streams(tmp_path):
    writer = ArchiveWriter(root_dir=tmp_path)
    live_path = writer.record_order({"ticker": "SPY-LIVE"}, source="live")
    ghost_path = writer.record_order({"ticker": "SPY-GHOST"}, source="ghost")

    assert "/orders/live/" in str(live_path)
    assert "/orders/ghost/" in str(ghost_path)

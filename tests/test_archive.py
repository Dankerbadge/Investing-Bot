import json

from investing_bot.archive import ArchiveWriter


def test_archive_writer_appends_jsonl(tmp_path):
    writer = ArchiveWriter(root_dir=tmp_path)
    path = writer.record_signal({"ticker": "SPY-TEST", "net_edge": 0.0123})

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["ticker"] == "SPY-TEST"
    assert "recorded_at" in payload

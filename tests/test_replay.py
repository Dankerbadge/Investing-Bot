import json

from investing_bot.replay import replay_archive_stream, replay_records


def test_replay_records_is_deterministic():
    rows = [
        {"recorded_at": "2026-04-04T10:00:05Z", "candidate_key": "B", "score": 0.2},
        {"recorded_at": "2026-04-04T10:00:01Z", "candidate_key": "A", "score": -0.1},
    ]

    def decide(row):
        return "trade" if float(row.get("score") or 0) > 0 else "skip"

    one = replay_records(rows=rows, decision_fn=decide)
    two = replay_records(rows=list(reversed(rows)), decision_fn=decide)
    assert one.deterministic_signature == two.deterministic_signature
    assert one.actions_by_type == {"skip": 1, "trade": 1}


def test_replay_archive_stream_reads_live_jsonl(tmp_path):
    stream_dir = tmp_path / "chain_snapshots" / "live"
    stream_dir.mkdir(parents=True, exist_ok=True)
    target = stream_dir / "2026-04-04.jsonl"
    target.write_text(
        "\n".join(
            [
                json.dumps({"recorded_at": "2026-04-04T10:00:00Z", "candidate_key": "X", "score": 1}),
                json.dumps({"recorded_at": "2026-04-04T10:01:00Z", "candidate_key": "Y", "score": -1}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = replay_archive_stream(
        archive_root=tmp_path,
        stream="chain_snapshots",
        source="live",
        decision_fn=lambda row: "trade" if float(row.get("score") or 0) > 0 else "skip",
    )
    assert result.replayed_count == 2
    assert result.actions_by_type["trade"] == 1
    assert result.actions_by_type["skip"] == 1

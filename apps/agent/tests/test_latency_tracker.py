import logging

from sam.latency.tracker import MAX_RETAINED_SAMPLES, LatencyTracker


def test_tracker_retains_only_recent_turns_but_counts_all_turns():
    tracker = LatencyTracker(logging.getLogger("test.latency"), enabled=False)

    for turn in range(1, MAX_RETAINED_SAMPLES + 3):
        tracker.record_turn({"e2e_latency": turn / 1000})

    snapshot = tracker.as_dict()

    assert snapshot["turns"] == MAX_RETAINED_SAMPLES + 2
    assert len(tracker._samples) == MAX_RETAINED_SAMPLES
    assert snapshot["last"]["index"] == MAX_RETAINED_SAMPLES + 2
    assert snapshot["response_delay_avg_ms"] == MAX_RETAINED_SAMPLES / 2 + 2.5


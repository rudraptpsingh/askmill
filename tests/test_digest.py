import json

from askmill.digest import codex_transcript, digest, split
from askmill.runner import Session


def write_rollout(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")


def test_codex_transcript_keeps_conversation_and_stop_reason_drops_tool_output(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    write_rollout(rollout, [
        {"timestamp": "2026-11-03T01:00:00Z", "type": "session_meta", "payload": {"cwd": "/work/Powerlex"}},
        {"timestamp": "2026-11-03T01:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>noise</environment_context>"}]}},
        {"timestamp": "2026-11-03T01:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Fix the query integration"}]}},
        {"timestamp": "2026-11-03T01:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "output": "SECRET TOOL OUTPUT " * 100}},
        {"timestamp": "2026-11-03T01:00:04Z", "type": "response_item", "payload": {"type": "reasoning", "summary": [{"type": "summary_text", "text": "**Checking the adapter**"}]}},
        {"timestamp": "2026-11-03T01:00:05Z", "type": "event_msg", "payload": {"type": "agent_message", "message": "Adapter fixed; tests pass."}},
        {"timestamp": "2026-11-03T01:00:06Z", "type": "event_msg", "payload": {"type": "task_complete", "error": {"message": "You've hit your usage limit."}}},
    ])
    text = codex_transcript(rollout)
    assert "cwd: /work/Powerlex" in text
    assert "USER: Fix the query integration" in text
    assert "ASSISTANT: Adapter fixed; tests pass." in text
    assert "Checking the adapter" in text
    assert "STOPPED: You've hit your usage limit." in text
    assert "environment_context" not in text and "SECRET TOOL OUTPUT" not in text


def test_codex_transcript_tail_keeps_the_first_ask_and_the_latest_progress(tmp_path):
    rollout = tmp_path / "rollout.jsonl"
    events = [{"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Original goal"}]}}]
    events += [{"type": "event_msg", "payload": {"type": "agent_message", "message": f"step {i}"}} for i in range(500)]
    write_rollout(rollout, events)
    text = codex_transcript(rollout, tail_chars=400)
    assert "Original goal" in text and "step 499" in text and "step 3\n" not in text


def test_split_respects_the_size_and_keeps_lines_whole():
    text = "\n".join(f"line {i} " + "x" * 50 for i in range(100))
    parts = split(text, 500)
    assert len(parts) > 1 and all(len(p) <= 500 for p in parts)
    assert "\n".join(parts) == text


def test_digest_maps_chunks_then_reduces_with_receipts(endpoint, tmp_path):
    profile, state = endpoint
    state["answer"] = "progress note"
    text = "\n".join(f"ASSISTANT: did thing {i} " + "y" * 80 for i in range(60))
    with Session(profile, tmp_path / "store", [str(tmp_path / "lock")]) as session:
        out = digest(session, text, focus="progress", chunk_chars=1200, max_tokens=64, timeout=30)
    assert out["status"] == "completed"
    assert out["final"] == "progress note"
    assert out["chunks"] > 1
    assert len(state["calls"]) == out["chunks"] + out["reduce_calls"]
    assert all(r for r in out["receipts"])
    prompts = [c[1]["messages"][-1]["content"] for c in state["calls"]]
    assert "progress" in prompts[0] and "did thing 0" in prompts[0]
    assert "progress note" in prompts[-1]


def test_digest_reports_incomplete_parts(endpoint, tmp_path):
    profile, state = endpoint
    state["complete"] = False
    with Session(profile, tmp_path / "store", [str(tmp_path / "lock")]) as session:
        out = digest(session, "USER: hello\nASSISTANT: hi", focus="progress", chunk_chars=1000, max_tokens=16, timeout=30)
    assert out["status"] == "incomplete"

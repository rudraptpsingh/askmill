"""Digest long text with a small local model: summarize chunks, then merge the summaries.

Every model call is an ordinary Session.run (pinned profile, lease, receipt). Also reads Codex
session transcripts (rollout JSONL) into a condensed conversation: user asks, assistant replies,
reasoning headings and the stop reason; tool calls and their output are left out.
"""

import json
from pathlib import Path

from .contract import Request

MAP_PROMPT = (
    "You are reviewing part {i} of {n} of a coding-agent session transcript.\n"
    "Focus: {focus}\n"
    "Write a short factual summary of this part: what was asked, what was done or decided, "
    "what was verified, what failed or is unfinished. Use plain bullets. Quote file names, "
    "commits, numbers and errors exactly. Do not invent anything not in the text.\n\n"
    "--- transcript part {i} of {n} ---\n{text}\n--- end ---"
)
REDUCE_PROMPT = (
    "Below are summaries of consecutive parts of {what}, in order.\n"
    "Focus: {focus}\n"
    "Merge them into one report with these headings: Goal, Done, In progress when it stopped, "
    "Open issues and next steps. Later parts override earlier ones. Keep exact names, commits "
    "and numbers. Do not invent anything not in the summaries. Be concise: at most 8 bullets per "
    "heading, merging repeats.\n\n{text}"
)

# Line types worth keeping; everything else (tool calls, outputs, token counts) is skipped
# before JSON parsing, which matters for multi-gigabyte transcripts.
_KEEP = ('"session_meta"', '"role":"user"', '"role": "user"', '"agent_message"', '"summary_text"', '"task_complete"',
         '"role":"assistant"', '"role": "assistant"')
_NOISE = ("<environment_context", "<user_instructions", "# AGENTS.md instructions", "<in-app-browser-context",
          "<turn_aborted", "<subagent_notification")


_WORKING = "(working on) "


def _clip(text, limit=2000):
    text = " ".join(text.split()) if len(text) > limit else text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def codex_transcript(path, tail_chars=None):
    """Condensed text of a Codex rollout file. With tail_chars, keep the first user ask and the
    last tail_chars characters (the latest progress)."""
    lines, first_ask, last_assistant, cwd = [], None, None, None
    with open(path, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            if not any(k in raw for k in _KEEP):
                continue
            try:
                event = json.loads(raw)
            except ValueError:
                continue
            p = event.get("payload") or {}
            when = (event.get("timestamp") or "")[:16].replace("T", " ")
            prefix = f"[{when}] " if when else ""
            kind = event.get("type")
            if kind == "session_meta":
                if p.get("cwd") and p.get("cwd") != cwd:
                    cwd = p["cwd"]
                    lines.append(f"cwd: {cwd}")
            elif kind == "response_item" and p.get("type") == "message":
                text = "\n".join(c.get("text", "") for c in p.get("content") or [] if isinstance(c, dict))
                if not text.strip() or any(text.lstrip().startswith(n) for n in _NOISE):
                    continue
                if p.get("role") == "user":
                    line = f"{prefix}USER: {_clip(text)}"
                    first_ask = first_ask or line
                    lines.append(line)
                elif p.get("role") == "assistant" and text.strip() != last_assistant:
                    last_assistant = text.strip()
                    lines.append(f"{prefix}ASSISTANT: {_clip(text)}")
            elif kind == "response_item" and p.get("type") == "reasoning":
                # Runs of reasoning headings collapse into one "(working on)" line.
                heads = [_clip(s["text"], 200).strip("* ") for s in p.get("summary") or [] if s.get("text")]
                if not heads:
                    continue
                if lines and lines[-1].split("] ", 1)[-1].startswith(_WORKING):
                    lines[-1] += "; " + "; ".join(heads)
                else:
                    lines.append(f"{prefix}{_WORKING}" + "; ".join(heads))
            elif kind == "event_msg" and p.get("type") == "agent_message":
                text = (p.get("message") or "").strip()
                if text and text != last_assistant:
                    last_assistant = text
                    lines.append(f"{prefix}ASSISTANT: {_clip(text)}")
            elif kind == "event_msg" and p.get("type") == "task_complete" and p.get("error"):
                lines.append(f"{prefix}STOPPED: {_clip(str(p['error'].get('message', p['error'])), 300)}")
    text = "\n".join(lines)
    if tail_chars and len(text) > tail_chars:
        tail = text[-tail_chars:]
        tail = tail[tail.find("\n") + 1:]
        head = [line for line in lines[:3] if line.startswith("cwd:")]
        text = "\n".join(head + ([first_ask] if first_ask else []) + ["[… earlier conversation omitted …]", tail])
    return text


def split(text, size):
    """Split on line boundaries into parts of at most `size` characters (long lines are cut)."""
    parts, current = [], []
    length = 0
    for line in text.split("\n"):
        while len(line) > size:
            if current:
                parts.append("\n".join(current))
                current, length = [], 0
            parts.append(line[:size])
            line = line[size:]
        if current and length + 1 + len(line) > size:
            parts.append("\n".join(current))
            current, length = [], 0
        current.append(line)
        length += len(line) + (1 if length else 0)
    if current:
        parts.append("\n".join(current))
    return parts


def digest(session, text, *, focus, what="one session transcript", chunk_chars=14000, max_tokens=900, timeout=600,
           reduce_tokens=None):
    """Map each chunk to a summary, then reduce (repeatedly if needed) to one report. Reduce calls
    get reduce_tokens (default twice max_tokens): a merged report is longer than one part's."""
    reduce_tokens = reduce_tokens or 2 * max_tokens
    receipts, complete = [], True

    def ask(prompt, tokens=max_tokens):
        nonlocal complete
        result = session.run(Request(prompt=prompt, max_tokens=tokens, timeout=timeout))
        receipts.append(result.receipt_id)
        complete = complete and result.complete
        return result.text.strip()

    parts = split(text, chunk_chars)
    summaries = [ask(MAP_PROMPT.format(i=i + 1, n=len(parts), focus=focus, text=part)) for i, part in enumerate(parts)]
    reduce_calls = 0
    while True:
        joined = "\n\n".join(f"## Part {i + 1}\n{s}" for i, s in enumerate(summaries))
        if len(joined) <= chunk_chars or len(summaries) == 1:
            final = ask(REDUCE_PROMPT.format(what=what, focus=focus, text=joined), reduce_tokens)
            reduce_calls += 1
            break
        groups = split(joined, chunk_chars)
        summaries = [ask(REDUCE_PROMPT.format(what=what, focus=focus, text=g), reduce_tokens) for g in groups]
        reduce_calls += len(groups)
    return {
        "schema_version": "askmill.digest.v1",
        "status": "completed" if complete else "incomplete",
        "final": final,
        "chunks": len(parts),
        "reduce_calls": reduce_calls,
        "receipts": receipts,
        "domain_acceptance": "unverified",
    }


def digest_codex_sessions(session, paths, *, focus, tail_chars=60000, chunk_chars=14000, max_tokens=900, timeout=600,
                          on_session=None):
    """One digest per Codex session, then one combined report across them. on_session(reports) is
    called after each session so callers can save partial progress."""
    reports = []
    for path in paths:
        text = codex_transcript(path, tail_chars=tail_chars)
        cwd = next((line[5:] for line in text.split("\n", 3) if line.startswith("cwd: ")), "")
        result = digest(session, text, focus=focus, chunk_chars=chunk_chars, max_tokens=max_tokens, timeout=timeout)
        reports.append({"session": Path(path).name, "cwd": cwd, **result})
        if on_session:
            on_session(reports)
    combined = digest(
        session,
        "\n\n".join(f"# Session {r['session']} (cwd {r['cwd']})\n{r['final']}" for r in reports),
        focus=focus, what="several coding-agent sessions on the same product",
        chunk_chars=chunk_chars, max_tokens=2 * max_tokens, timeout=timeout, reduce_tokens=max(2 * max_tokens, 2400),
    )
    status = "completed" if combined["status"] == "completed" and all(r["status"] == "completed" for r in reports) else "incomplete"
    return {"schema_version": "askmill.codex-digest.v1", "status": status, "combined": combined, "sessions": reports,
            "domain_acceptance": "unverified"}

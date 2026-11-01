"""Exercise the published a4 CLI with a synthetic Ollama stub; no inference."""

import argparse
import copy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zipfile import ZipFile

WHEEL_SHA256 = "6a17f43435df1fd9388331903b2383d4f8fb94ffd48e3fc2acafc4be2edb2745"
FIXTURE = Path(__file__).resolve().parent
ANSWER = '{"source_id":"part-a"}'


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="New private output directory"
    )
    args = parser.parse_args()
    assert hashlib.sha256(args.wheel.read_bytes()).hexdigest() == WHEEL_SHA256
    distribution = importlib.metadata.distribution("askmill")
    assert distribution.version == "0.1.0a4"
    assert (
        "site-packages" in Path(distribution.locate_file("askmill/__init__.py")).parts
    )
    with ZipFile(args.wheel) as wheel:
        for name in wheel.namelist():
            if name.startswith("askmill/") and name.endswith(".py"):
                assert Path(distribution.locate_file(name)).read_bytes() == wheel.read(
                    name
                ), name
    executable = Path(sys.prefix) / "bin/askmill"
    assert (
        subprocess.check_output([str(executable), "--version"], text=True).strip()
        == "askmill 0.1.0a4"
    )
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)  # Never replace old execution evidence.
    task = json.loads((FIXTURE / "request.json").read_text())
    assert (
        task["sources"][0]["content_sha256"]
        == hashlib.sha256((FIXTURE / "source.txt").read_bytes()).hexdigest()
    )
    assert task["response_schema"]["sha256"] == digest(
        task["response_schema"]["document"]
    )
    state = {"text": ANSWER, "complete": True, "calls": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, value):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps(value).encode())

        def do_GET(self):
            if self.path == "/api/version":
                self.reply({"version": "0.40.13"})
            elif self.path == "/api/tags":
                self.reply(
                    {
                        "models": [
                            {"name": "fixture:source-id", "digest": "sha256:synthetic"}
                        ]
                    }
                )
            else:
                self.send_error(404)

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/api/show":
                self.reply({"capabilities": ["completion"]})
            elif self.path == "/api/chat":
                state["calls"].append(payload)
                self.reply(
                    {
                        "model": "fixture:source-id",
                        "done": True,
                        "done_reason": "stop" if state["complete"] else "length",
                        "eval_count": 5,
                        "message": {"content": state["text"]},
                    }
                )
            else:
                self.send_error(404)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = out / "profiles.json"
    write(
        config,
        {
            "schema_version": "askmill.profiles.v1",
            "profiles": {
                "fixture": {
                    "provider": "ollama",
                    "model": "fixture:source-id",
                    "revision": "sha256:synthetic",
                    "capabilities": ["text"],
                    "base_url": f"http://127.0.0.1:{server.server_port}",
                }
            },
        },
    )
    cases = {}

    def run(name, body, exit_code):
        folder = out / name
        folder.mkdir()
        write(folder / "request.json", body)
        command = [
            str(executable),
            "--config",
            str(config),
            "--store",
            str(folder / "receipts"),
            "--lease",
            str(out / "synthetic-stub.lock"),
            "run",
            "--profile",
            "fixture",
            "--request",
            str(folder / "request.json"),
        ]
        process = subprocess.run(command, capture_output=True, text=True, timeout=25)
        (folder / "stdout.json").write_text(process.stdout)
        (folder / "stderr.txt").write_text(process.stderr)
        value = json.loads(process.stdout)
        assert process.returncode == exit_code, process.stdout + process.stderr
        cases[name] = {
            "exit_code": exit_code,
            "result": f"{name}/stdout.json",
            "status": value["status"],
        }
        return value, command, folder

    try:
        for name, text, complete, exit_code, valid in [
            ("success", ANSWER, True, 0, True),
            ("schema-invalid", '{"source_id":"outside-scope"}', True, 4, False),
            ("truncated-json", '{"source_id":', False, 3, False),
            ("truncated-valid-json", ANSWER, False, 3, True),
        ]:
            state.update(text=text, complete=complete)
            result, command, folder = run(name, task, exit_code)
            assert result["schema_version"] == "askmill.result.v2"
            assert result["complete"] is complete and result["text"] == text
            assert result["response_validation"]["valid"] is valid
            assert (
                result["response_validation"]["schema_sha256"]
                == task["response_schema"]["sha256"]
            )
            assert result["domain_acceptance"] == "unverified"
            receipt_path = folder / "receipts" / (result["receipt_id"] + ".json")
            receipt = json.loads(receipt_path.read_text())
            content = receipt["content"]
            assert digest(content) == receipt["sha256"]
            assert content["schema_version"] == "askmill.receipt.v2"
            assert content["request"] == task and content["result"] == result
            assert content["raw_response"]["message"]["content"] == text
            assert (
                digest({key: content[key] for key in ("request", "profile", "runtime")})
                == result["receipt_id"]
            )
            settlement = json.loads(
                (
                    folder / "receipts/settlements" / (result["session_id"] + ".json")
                ).read_text()
            )
            assert digest(settlement["content"]) == settlement["sha256"]
            assert (
                settlement["content"]["worker_reaped"]
                and not settlement["content"]["quarantined"]
            )
            assert (
                settlement["content"]["external_request_settlement"] == "acknowledged"
            )
            cases[name]["receipt"] = str(receipt_path.relative_to(out))
            if name == "success":
                count = len(state["calls"])
                replay = subprocess.run(
                    command, capture_output=True, text=True, timeout=25
                )
                assert replay.returncode == 0
                replay_value = json.loads(replay.stdout)
                assert (
                    replay_value["replayed"]
                    and replay_value["receipt_id"] == result["receipt_id"]
                )
                assert len(state["calls"]) == count
                (folder / "replay.json").write_text(replay.stdout)
                cases[name]["replay_verified"] = True
        count = len(state["calls"])
        unsupported = copy.deepcopy(task)
        unsupported["response_schema"]["document"] = {"type": "string", "pattern": "x"}
        unsupported["response_schema"]["sha256"] = digest(
            unsupported["response_schema"]["document"]
        )
        rejected, _, _ = run("schema-rejected", unsupported, 2)
        assert "Unsupported response schema keywords: pattern" in rejected["error"]
        wrong_pin = copy.deepcopy(task)
        wrong_pin["response_schema"]["sha256"] = "0" * 64
        rejected, _, _ = run("schema-pin-rejected", wrong_pin, 2)
        assert "Response schema SHA256 mismatch" in rejected["error"]
        assert len(state["calls"]) == count == 4
        assert all(
            payload["format"] == task["response_schema"]["document"]
            for payload in state["calls"]
        )
        write(out / "wire-requests.json", state["calls"])
        assert not (out / "synthetic-stub.lock.unsettled").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    summary = {
        "fixture": "askmill.installed-a4-source-id.v1",
        "runner": "0.1.0a4",
        "wheel_sha256": WHEEL_SHA256,
        "schema_sha256": task["response_schema"]["sha256"],
        "transport": "synthetic local HTTP stub",
        "actual_model_inference": False,
        "model_fallback": False,
        "producer_edited": False,
        "consumer_acceptance": "pending",
        "cases": cases,
        "provider_generate_calls": len(state["calls"]),
    }
    write(out / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

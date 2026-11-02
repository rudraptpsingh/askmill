"""Offline software controls: fake provider/tokenizer, never model inference."""

import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from askmill import embedding


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class FakeTokenizer:
    @classmethod
    def from_file(cls, path):
        return cls()

    def no_truncation(self):
        pass

    def encode(self, text, add_special_tokens=True):
        return types.SimpleNamespace(ids=[1, 2, 3])


class FakeProcess:
    pid = 987654

    def poll(self):
        return None


class FakeResourceProcess:
    def __init__(self, pid):
        self.pid = pid

    def create_time(self):
        return 100.0

    def children(self, recursive=True):
        return []

    def is_running(self):
        return True

    def memory_info(self):
        return types.SimpleNamespace(rss=1)


class EmbeddingControls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = self.root / "store"
        (self.store / "blobs").mkdir(parents=True)
        self.tok = self.pin("tokenizer.json", b'{"fixture":"no real tokenizer"}')
        blob = b"software config"
        blob_sha = digest(blob)
        (self.store / "blobs" / ("sha256-" + blob_sha)).write_bytes(blob)
        tok_raw = Path(self.tok["path"]).read_bytes()
        (self.store / "blobs" / ("sha256-" + self.tok["sha256"])).write_bytes(tok_raw)
        manifest = {
            "config": {"digest": "sha256:" + blob_sha, "size": len(blob)},
            "layers": [
                {
                    "name": "tokenizer.json",
                    "digest": "sha256:" + self.tok["sha256"],
                    "size": len(tok_raw),
                }
            ],
        }
        self.manifest = self.pin("manifest.json", json.dumps(manifest).encode())
        binary = self.pin("ollama", b"fake executable")
        lib = self.pin("runtime.dat", b"fake runtime")
        self.gate = self.pin(
            "gate.py",
            b'def authorize(profile,request,stage): return True\ndef reserve(profile,request,sha): return "synthetic-reservation"\ndef finalize(reservation,settlement): return True\n',
        )
        self.lease1 = self.root / "lock1"
        self.lease2 = self.root / "lock2"
        self.lease1.touch()
        self.lease2.touch()
        self.profile = {
            "schema_version": "askmill.embedding-profile.v1",
            "provider": "ollama-owned",
            "capabilities": ["embedding"],
            "model": "fixture-encoder",
            "model_revision": self.manifest["sha256"],
            "dimensions": 2,
            "context_tokens": 16,
            "tokenizer": self.tok,
            "tokenizers_version": "fixture-tokenizers",
            "psutil_version": "fixture-psutil",
            "model_manifest": self.manifest,
            "model_store": str(self.store),
            "provider_binary": binary,
            "runtime_files": [lib],
            "provider_version": "1.0.0",
            "context_gate": self.gate,
            "lease_paths": [str(self.lease1), str(self.lease2)],
            "min_available_bytes": 1,
            "max_owned_rss_bytes": 999999,
            "timeout_seconds": 30,
        }
        text = "synthetic software fixture"
        self.request = {
            "schema_version": "askmill.embedding-batch.v1",
            "batch_id": "fixture-batch",
            "scope_sha256": "a" * 64,
            "items": [{"id": "fixture", "text": text, "sha256": digest(text.encode())}],
        }
        self.profile_raw = json.dumps(self.profile).encode()
        self.request_raw = json.dumps(self.request).encode()
        self.calls = []
        self.marker_observations = []

    def tearDown(self):
        self.tmp.cleanup()

    def pin(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return {"path": str(path), "sha256": digest(data)}

    def fake_http(self, endpoint, path, data=None, timeout=10):
        self.calls.append((path, data))
        if path == "/api/embed":
            self.marker_observations.append(
                all(
                    Path(str(p) + ".unsettled").exists()
                    for p in (self.lease1, self.lease2)
                )
            )
        if path == "/api/version":
            return {"version": "1.0.0"}
        if path == "/api/tags":
            return {
                "models": [
                    {"name": "fixture-encoder", "digest": self.manifest["sha256"]}
                ]
            }
        if path == "/api/show":
            return {"capabilities": ["embedding"]}
        if path == "/api/ps":
            if any(x[0] == "/api/embed" and x[1]["input"] == [] for x in self.calls):
                return {"models": []}
            return {"models": [{"name": "fixture-encoder", "context_length": 16}]}
        if path == "/api/embed" and data["input"] == []:
            return {}
        if path == "/api/embed":
            return {
                "model": "fixture-encoder",
                "prompt_eval_count": 3,
                "embeddings": [[1.0, 0.0]],
            }
        raise AssertionError(path)

    def run_fake(self, http=None):
        fake_tokenizers = types.SimpleNamespace(
            Tokenizer=FakeTokenizer, __version__="fixture-tokenizers"
        )
        fake_psutil = types.SimpleNamespace(
            __version__="fixture-psutil",
            virtual_memory=lambda: types.SimpleNamespace(available=999999),
            Process=FakeResourceProcess,
        )
        with (
            patch.dict(
                sys.modules, {"tokenizers": fake_tokenizers, "psutil": fake_psutil}
            ),
            patch.object(embedding, "http", side_effect=http or self.fake_http),
            patch.object(embedding.subprocess, "Popen", return_value=FakeProcess()),
            patch.object(embedding.subprocess, "check_output", return_value="987654\n"),
            patch.object(embedding, "_stop_owned", return_value=True),
        ):
            return embedding.run_embedding(
                self.profile_raw,
                digest(self.profile_raw),
                self.request_raw,
                digest(self.request_raw),
                self.root / "output",
                self.profile["lease_paths"],
            )

    def test_one_data_and_one_cleanup_software_calls(self):
        result = self.run_fake()
        calls = [x for x in self.calls if x[0] == "/api/embed"]
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.marker_observations, [True, True])
        self.assertFalse(Path(str(self.lease1) + ".unsettled").exists())
        self.assertFalse(Path(str(self.lease2) + ".unsettled").exists())
        self.assertEqual(calls[0][1]["input"], [self.request["items"][0]["text"]])
        self.assertEqual(calls[1][1]["input"], [])
        self.assertEqual(result["provider_data_requests"], 1)
        self.assertEqual(result["cleanup_requests"], 1)
        self.assertFalse(result["silent_truncation"])
        settlement = json.loads((self.root / "output" / "settlement.json").read_text())
        self.assertTrue(settlement["data_acknowledged"])
        self.assertTrue(settlement["cleanup_acknowledged"])
        self.assertEqual(settlement["lease_handles_closed"], 2)

    def test_wrong_input_hash_never_reaches_provider(self):
        self.request["items"][0]["sha256"] = "b" * 64
        self.request_raw = json.dumps(self.request).encode()
        with self.assertRaises(ValueError):
            self.run_fake()
        self.assertEqual(self.calls, [])

    def test_timeout_quarantines_and_does_not_retry(self):
        def fail(endpoint, path, data=None, timeout=10):
            if path == "/api/embed" and data["input"]:
                self.calls.append((path, data))
                raise TimeoutError("synthetic uncertain dispatch")
            return self.fake_http(endpoint, path, data, timeout)

        with self.assertRaises(TimeoutError):
            self.run_fake(fail)
        self.assertEqual(len([x for x in self.calls if x[0] == "/api/embed"]), 1)
        self.assertTrue(Path(str(self.lease1) + ".unsettled").exists())
        self.assertTrue(Path(str(self.lease2) + ".unsettled").exists())
        self.assertFalse((self.root / "output" / "result.json").exists())

    def test_tokenizer_runtime_mismatch_refused(self):
        self.profile["tokenizers_version"] = "not-the-pinned-version"
        self.profile_raw = json.dumps(self.profile).encode()
        with self.assertRaisesRegex(ValueError, "runtime version differs"):
            self.run_fake()
        self.assertEqual(self.calls, [])

    def test_context_denial_never_reaches_provider(self):
        self.gate = self.pin(
            "gate-deny.py", b"def authorize(profile,request,stage): return False\n"
        )
        self.profile["context_gate"] = self.gate
        self.profile_raw = json.dumps(self.profile).encode()
        with self.assertRaisesRegex(ValueError, "context gate refused"):
            self.run_fake()
        self.assertEqual(self.calls, [])

    def test_revoked_context_retains_evidence_but_no_result(self):
        self.gate = self.pin(
            "gate-revoke.py",
            b'def authorize(profile,request,stage): return stage != "after"\ndef reserve(profile,request,sha): return "synthetic-reservation"\ndef finalize(reservation,settlement): return True\n',
        )
        self.profile["context_gate"] = self.gate
        self.profile_raw = json.dumps(self.profile).encode()
        with self.assertRaisesRegex(ValueError, "revoked after"):
            self.run_fake()
        self.assertTrue((self.root / "output" / "settlement.json").exists())
        self.assertFalse(
            json.loads((self.root / "output" / "context-recheck.json").read_text())[
                "authorized"
            ]
        )
        self.assertFalse((self.root / "output" / "result.json").exists())

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX crash control")
    def test_parent_crash_keeps_attempt_quarantined(self):
        def abrupt_exit(endpoint, path, data=None, timeout=10):
            if path == "/api/embed" and data["input"]:
                os._exit(47)
            return self.fake_http(endpoint, path, data, timeout)

        child = os.fork()
        if child == 0:
            try:
                self.run_fake(abrupt_exit)
            finally:
                os._exit(48)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 47)
        self.assertTrue(Path(str(self.lease1) + ".unsettled").exists())
        self.assertTrue(Path(str(self.lease2) + ".unsettled").exists())
        self.assertFalse((self.root / "output" / "result.json").exists())

    def test_unknown_context_allocation_refuses_delivery(self):
        def no_allocation(endpoint, path, data=None, timeout=10):
            if path == "/api/ps":
                self.calls.append((path, data))
                return {"models": []}
            return self.fake_http(endpoint, path, data, timeout)

        with self.assertRaisesRegex(ValueError, "allocation"):
            self.run_fake(no_allocation)
        self.assertFalse((self.root / "output" / "result.json").exists())

    def test_uncertain_cleanup_quarantines_without_retry(self):
        def cleanup_timeout(endpoint, path, data=None, timeout=10):
            if path == "/api/embed" and data["input"] == []:
                self.calls.append((path, data))
                raise TimeoutError("synthetic cleanup timeout")
            return self.fake_http(endpoint, path, data, timeout)

        with self.assertRaises(TimeoutError):
            self.run_fake(cleanup_timeout)
        receipt = json.loads((self.root / "output" / "settlement.json").read_text())
        self.assertEqual(receipt["data_requests_started"], 1)
        self.assertEqual(receipt["cleanup_requests"], 1)
        self.assertTrue(receipt["quarantined"])
        self.assertTrue(Path(str(self.lease1) + ".unsettled").exists())

    def test_extra_dimensions_and_token_mismatch_refused(self):
        def mismatch(endpoint, path, data=None, timeout=10):
            if path == "/api/embed" and data["input"]:
                self.calls.append((path, data))
                return {
                    "model": "fixture-encoder",
                    "prompt_eval_count": 2,
                    "embeddings": [[1.0, 0.0]],
                }
            return self.fake_http(endpoint, path, data, timeout)

        with self.assertRaisesRegex(ValueError, "token count"):
            self.run_fake(mismatch)
        self.assertFalse((self.root / "output" / "result.json").exists())


if __name__ == "__main__":
    unittest.main()


class CliRegistrationControls(unittest.TestCase):
    def test_embed_is_listed_from_explicit_registry_without_inference(self):
        import subprocess

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lock = root / "lock"
            lock.touch()
            registry = root / "profiles.json"
            registry.write_text(
                json.dumps(
                    {
                        "schema_version": "askmill.profiles.v1",
                        "profiles": {},
                        "embedding_profiles": {
                            "explicit": {
                                "path": str(root / "profile.json"),
                                "sha256": "a" * 64,
                            }
                        },
                        "lease_paths": [str(lock)],
                    }
                )
            )
            run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "askmill.cli",
                    "--config",
                    str(registry),
                    "list",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("explicit", json.loads(run.stdout)["embedding_profiles"])

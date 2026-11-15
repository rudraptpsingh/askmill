import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("timing", Path(__file__).resolve().parents[1] / "tools/inspect_generation_timing.py")
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


def receipt(response=None):
    request = {"prompt": "synthetic"}
    profile = {"provider": "ollama"}
    runtime = {"runner": "synthetic"}
    key = timing._digest_json({"request": request, "profile": profile, "runtime": runtime})
    content = {"schema_version": "askmill.receipt.v2", "key": key, "request": request, "profile": profile, "runtime": runtime, "result": {"receipt_id": key, "runtime": runtime, "replayed": False, "seconds": 3.0, "status": "incomplete"}, "raw_response": response if response is not None else {"load_duration": 5, "prompt_eval_duration": 8, "total_duration": 9, "prompt_eval_count": 2}}
    record = {"content": content, "sha256": timing._digest_json(content)}
    raw = json.dumps(record).encode()
    return raw, hashlib.sha256(raw).hexdigest()


class TimingInspection(unittest.TestCase):
    def test_boundaries_and_missing_values_remain_unknown(self):
        raw, pin = receipt()
        result = timing.inspect(raw, pin)
        self.assertEqual(result["provider_reported_durations"]["load_duration"], 5)
        self.assertIsNone(result["provider_reported_durations"]["eval_duration"])
        self.assertIsNone(result["session_startup_seconds"])
        self.assertIsNone(result["current_invocation_replayed"])
        self.assertEqual(result["model_residency_before_call"], "unknown")
        self.assertEqual(result["result_status"], "incomplete")
        self.assertNotIn("synthetic", json.dumps(result))

    def test_rejects_changed_bytes_and_bad_envelope(self):
        raw, pin = receipt()
        with self.assertRaises(ValueError):
            timing.inspect(raw + b" ", pin)
        obj = json.loads(raw)
        obj["content"]["result"]["seconds"] = 4
        modified = json.dumps(obj).encode()
        with self.assertRaises(ValueError):
            timing.inspect(modified, hashlib.sha256(modified).hexdigest())

    def test_rejects_invalid_or_boolean_durations_and_counts(self):
        for value in (-1, True, 1.5, "4"):
            with self.subTest(value=value):
                raw, pin = receipt({"load_duration": value})
                with self.assertRaises(ValueError):
                    timing.inspect(raw, pin)
        raw, pin = receipt({"eval_count": -1})
        with self.assertRaises(ValueError):
            timing.inspect(raw, pin)

    def test_rejects_forged_binding_even_with_new_checksum(self):
        raw, _ = receipt()
        obj = json.loads(raw)
        obj["content"]["result"]["receipt_id"] = "bad"
        obj["sha256"] = timing._digest_json(obj["content"])
        changed = json.dumps(obj).encode()
        with self.assertRaises(ValueError):
            timing.inspect(changed, hashlib.sha256(changed).hexdigest())

    def test_rejects_duplicate_json_keys(self):
        raw = b'{"content":{},"content":{},"sha256":"x"}'
        with self.assertRaises(ValueError):
            timing.inspect(raw, hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    unittest.main()

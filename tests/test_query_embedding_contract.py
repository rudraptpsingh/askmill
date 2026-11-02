"""Offline typed contract controls; synthetic vectors are software fixtures only."""

import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
spec = importlib.util.spec_from_file_location(
    "query_embedding_contract",
    Path(__file__).resolve().parents[1] / "tools/query_embedding_contract.py",
)
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.schema_dir = os.environ.get("ASKMILL_QUERY_SCHEMA_DIR")
        if not self.schema_dir:
            self.skipTest("Supply pinned Query schema directory")
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.profile = self.pin("askmill-profile.json", b'{"synthetic":"profile"}')
        provider = {"model": "fixture", "nested": {"z": 2, "a": 1}}
        model_input = {"model": "fixture", "context": 8192}
        self.prov = self.pin("provider.json", json.dumps(provider).encode())
        self.inp = self.pin("input.json", json.dumps(model_input).encode())
        self.grant = self.pin("grant.json", b'{"synthetic":true}')
        h = "a" * 64
        scope = {
            "principalRef": "fixture:principal",
            "workspaceId": "fixture:workspace",
            "databaseId": "fixture:database",
            "policyRevision": 1,
            "selectionSha256": h,
            "jobId": "fixture:job",
            "sourceSha256": h,
            "originalSha256": h,
            "nativePackageSha256": h,
            "processedSha256": h,
            "sourceVersionId": "fixture:version",
            "configSha256": h,
            "indexedInputSourceStageSha256": h,
            "queryTargetSha256": None,
        }
        profile = {
            "askmill_profile_name": "fixture",
            "askmill_profile_sha256": self.profile["sha256"],
            "provider_profile": self.prov,
            "provider_profile_canonical_sha256": contract.digest(
                contract.canonical(provider)
            ),
            "model_input_profile": self.inp,
            "model_input_profile_canonical_sha256": contract.digest(
                contract.canonical(model_input)
            ),
            "dimensions": 768,
            "namespace": "fixture:namespace",
        }
        text = "synthetic complete embedding input"
        self.request = {
            "schema": "powerlex.query.embedding-batch.v1",
            "batch_id": "fixture:batch",
            "kind": "documents",
            "scope": scope,
            "source_read_before": self.grant,
            "profile": profile,
            "items": [
                {
                    "id": "fixture:item",
                    "task_id": "fixture:task",
                    "source_sha256": h,
                    "chunk_id": "fixture:chunk",
                    "source_text_sha256": h,
                    "embedding_input": text,
                    "embedding_input_sha256": contract.digest(text.encode()),
                }
            ],
            "policy": {
                "maximum_provider_embedding_requests": 1,
                "retries": 0,
                "fallback": False,
                "downloads": False,
                "silent_truncation": False,
            },
        }
        self.request_raw = json.dumps(self.request).encode()
        self.evidence = self.pin("receipt.json", b'{"synthetic":true}')
        values = [1.0] + [0.0] * 767
        self.response = {
            "schema": "powerlex.query.embedding-batch-result.v1",
            "batch_id": "fixture:batch",
            "request_sha256": contract.digest(self.request_raw),
            "scope_sha256": contract.digest(contract.canonical(scope)),
            "profile": profile,
            "rows": [
                {
                    "id": "fixture:item",
                    "embedding_input_sha256": contract.digest(text.encode()),
                    "vector_sha256": contract.digest(struct.pack("<768f", *values)),
                    "values": values,
                }
            ],
            "actual_provider_embedding_requests": 1,
            "actual_input_tokens": 2,
            "runtime_receipt": self.evidence,
            "model_usage_receipt": self.evidence,
            "resource_lease_receipt": self.evidence,
            "cleanup_receipt": self.evidence,
            "live_model_inference": True,
            "silent_truncation": False,
            "generation_calls": 0,
            "retries": 0,
            "fallback": False,
            "downloads": 0,
            "source_quality_approval_granted": False,
            "legal_answer_eligible": False,
        }

    def tearDown(self):
        self.tmp.cleanup()

    def pin(self, name, raw):
        p = self.root / name
        p.write_bytes(raw)
        return {"path": str(p), "sha256": contract.digest(raw)}

    def test_inspection_does_not_authorize(self):
        got = contract.prepare(self.request_raw, self.profile, self.schema_dir)
        self.assertFalse(got["dispatch_authorized"])
        self.assertEqual(got["source_read_authority"], "not_verified")

    def test_synthetic_response_roundtrip_and_no_origin_claim(self):
        got = contract.verify_response(
            self.request_raw,
            json.dumps(self.response).encode(),
            self.profile,
            self.schema_dir,
        )
        self.assertEqual(got["rows"], 1)
        self.assertEqual(got["receipt_origins"], "not_authenticated")

    def test_vector_tampering_refused(self):
        self.response["rows"][0]["values"][0] = 0.5
        with self.assertRaisesRegex(ValueError, "hash or normalization"):
            contract.verify_response(
                self.request_raw,
                json.dumps(self.response).encode(),
                self.profile,
                self.schema_dir,
            )

    def test_source_binding_and_canonical_profile_refused(self):
        self.request["items"][0]["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "source binding"):
            contract.prepare(
                json.dumps(self.request).encode(), self.profile, self.schema_dir
            )
        self.request["items"][0]["source_sha256"] = "a" * 64
        self.request["profile"]["provider_profile_canonical_sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "Canonical"):
            contract.prepare(
                json.dumps(self.request).encode(), self.profile, self.schema_dir
            )

    def test_inspector_refuses_extra_or_unpinned_receipt(self):
        self.response["rows"][0]["id"] = "different"
        with self.assertRaisesRegex(ValueError, "identity"):
            contract.verify_response(
                self.request_raw,
                json.dumps(self.response).encode(),
                self.profile,
                self.schema_dir,
            )
        self.response["rows"][0]["id"] = "fixture:item"
        self.response["cleanup_receipt"]["sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "checksum"):
            contract.verify_response(
                self.request_raw,
                json.dumps(self.response).encode(),
                self.profile,
                self.schema_dir,
            )

    def test_over_32_refuses_no_truncation(self):
        self.request["items"] = self.request["items"] * 33
        with self.assertRaisesRegex(ValueError, "limit is 32"):
            contract.prepare(
                json.dumps(self.request).encode(), self.profile, self.schema_dir
            )


if __name__ == "__main__":
    unittest.main()

"""Synthetic adapter controls only; no model, provider, or real source calls."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "embedding_bridge",
    Path(__file__).resolve().parents[1] / "tools/embedding_bridge.py",
)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

FAKE_ADAPTER = """
from contextlib import contextmanager
import hashlib, json
from pathlib import Path
import numpy as np
@contextmanager
def encoder_session(config, runtime_directory, planned_inputs=None):
    out = Path(runtime_directory)
    profile = json.loads(Path(config["provider_profile"]["path"]).read_text())
    def encode(texts, destination, label):
        matrix=np.zeros((len(texts),768),dtype='<f4')
        matrix[:,0]=1
        path=Path(destination)/(label+'.npy')
        np.save(path,matrix,allow_pickle=False)
        events=[{'input_sha256s':[hashlib.sha256(t.encode()).hexdigest() for t in texts], 'actual_tokens':len(texts), 'actual_provider_receipt':{'prompt_eval_count':len(texts)}}]
        report={'model_calls':1,'inputs':len(texts),'silent_truncation':False,'Float32_row_sha256s':[hashlib.sha256(v.tobytes()).hexdigest() for v in matrix],'events':events,'values':{'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}}
        (Path(destination)/(label+'-receipt.json')).write_text(json.dumps(report))
        return matrix,report
    yield profile,encode
    (out/'cleanup.json').write_text(json.dumps({'owned_server_stopped':True,'unload_verified':True}))
"""


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.profile = self.pin(
            "profile.json",
            json.dumps(
                {
                    "model": "embeddinggemma-2:270m",
                    "dimensions": 768,
                    "normalized": True,
                    "provider": "ollama_local_mlx_nvfp4",
                    "max_context_tokens": 8192,
                    "pooling": "mean",
                    "tokenizer_sha256": "4d777ef5bdc1aa36227abdfb77c3e49e7b9c892d16e1b6bda41c393504828be4",
                    "runtime": {
                        "api_model_digest": "20c5a2af114e1813484d1611b27a57c33398aee4f59c39359c5a28af9d1547e7"
                    },
                }
            ).encode(),
        )
        self.adapter = self.pin("fake_adapter.py", FAKE_ADAPTER.encode())
        self.grant = self.pin("grant.json", b'{"synthetic":true}')
        self.source_gate = self.pin(
            "source_gate.py", b"def verify_source_read(request, config): return True\n"
        )
        self.config = self.pin(
            "config.json",
            json.dumps(
                {
                    "provider_profile": self.profile,
                    "host_scripts": str(self.root),
                    "resource_policy": {"synthetic": True},
                }
            ).encode(),
        )
        self.dependencies = [
            self.pin(name, b"# synthetic offline control\n")
            for name in (
                "cerc_resources.py",
                "run_regulatory_local_embeddings.py",
                "prepare_regulatory_local_embedding_inputs.py",
                "plan_regulatory_best_effort_embeddings.py",
            )
        ]
        self.registry = {
            "schema_version": "askmill.embedding-registry.v1",
            "profiles": {
                "fixture": {
                    "adapter": self.adapter,
                    "configuration": self.config,
                    "dependencies": self.dependencies,
                    "source_gate": self.source_gate,
                }
            },
        }
        text = "synthetic software only"
        self.request = {
            "schema_version": "askmill.embedding-request.v1",
            "mode": "documents",
            "source_read_ref": self.grant,
            "inputs": [
                {
                    "id": "row-1",
                    "text": text,
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                }
            ],
        }

    def tearDown(self):
        self.temp.cleanup()

    def pin(self, name, data):
        p = self.root / name
        p.write_bytes(data)
        return {"path": str(p), "sha256": hashlib.sha256(data).hexdigest()}

    def test_one_batch_artifact_and_receipt(self):
        result = bridge.run_batch(
            self.registry, "fixture", self.request, self.root / "out"
        )
        self.assertEqual(result["provider_model_calls"], 1)
        self.assertEqual(result["provider_profile_sha256"], self.profile["sha256"])
        self.assertEqual(
            result["inputs"][0]["sha256"], self.request["inputs"][0]["sha256"]
        )
        self.assertFalse(result["legal_answer_eligible"])

    def test_changed_text_refuses_before_adapter(self):
        self.request["inputs"][0]["text"] = "different"
        with self.assertRaisesRegex(ValueError, "digest"):
            bridge.run_batch(self.registry, "fixture", self.request, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_unregistered_or_ungated_refuses(self):
        with self.assertRaisesRegex(ValueError, "not registered"):
            bridge.run_batch(self.registry, "unknown", self.request, self.root / "out")
        self.config = self.pin(
            "config2.json",
            json.dumps(
                {"provider_profile": self.profile, "host_scripts": str(self.root)}
            ).encode(),
        )
        self.registry["profiles"]["fixture"]["configuration"] = self.config
        with self.assertRaisesRegex(ValueError, "resource policy"):
            bridge.run_batch(self.registry, "fixture", self.request, self.root / "out")

    def test_duplicate_ids_and_too_many_refused(self):
        self.request["inputs"] *= 2
        with self.assertRaisesRegex(ValueError, "digest"):
            bridge.request_check(self.request)
        self.request["inputs"] *= 17
        with self.assertRaisesRegex(ValueError, "32"):
            bridge.request_check(self.request)

    def test_nonfinite_vector_refuses_without_success_receipt(self):
        changed = FAKE_ADAPTER.replace("matrix[:,0]=1", "matrix[:,0]=float('nan')")
        self.registry["profiles"]["fixture"]["adapter"] = self.pin(
            "fake_bad.py", changed.encode()
        )
        with self.assertRaisesRegex(ValueError, "Non-finite"):
            bridge.run_batch(self.registry, "fixture", self.request, self.root / "out")
        self.assertFalse((self.root / "out" / "receipt.json").exists())
        self.assertTrue((self.root / "out" / "RESERVED.json").exists())

    def test_provider_token_mismatch_refused(self):
        changed = FAKE_ADAPTER.replace(
            "'prompt_eval_count':len(texts)", "'prompt_eval_count':0"
        )
        self.registry["profiles"]["fixture"]["adapter"] = self.pin(
            "fake_bad.py", changed.encode()
        )
        with self.assertRaisesRegex(ValueError, "token evidence"):
            bridge.run_batch(self.registry, "fixture", self.request, self.root / "out")
        self.assertFalse((self.root / "out" / "receipt.json").exists())

    def test_source_gate_refusal_stops_before_output(self):
        self.registry["profiles"]["fixture"]["source_gate"] = self.pin(
            "deny.py", b"def verify_source_read(request, config): return False\n"
        )
        with self.assertRaisesRegex(ValueError, "source-read"):
            bridge.run_batch(self.registry, "fixture", self.request, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_changed_dependency_refuses_before_output(self):
        Path(self.dependencies[0]["path"]).write_text("changed")
        with self.assertRaisesRegex(ValueError, "checksum"):
            bridge.run_batch(self.registry, "fixture", self.request, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_existing_output_refuses_replay(self):
        bridge.run_batch(self.registry, "fixture", self.request, self.root / "out")
        with self.assertRaises(FileExistsError):
            bridge.run_batch(self.registry, "fixture", self.request, self.root / "out")


if __name__ == "__main__":
    unittest.main()

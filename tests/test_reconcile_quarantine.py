"""Synthetic local marker-custody controls; no model or shared service."""

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "reconcile_quarantine",
    Path(__file__).resolve().parents[1] / "tools/reconcile_quarantine.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Controls(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.leases = []
        for i in range(2):
            p = self.root / f"lease-{i}"
            p.write_bytes(b"")
            m = Path(str(p) + ".unsettled")
            m.write_bytes(b"synthetic quarantine")
            a, b = p.stat(), m.stat()
            self.leases.append(
                {
                    "lease_path": str(p),
                    "lease_device": a.st_dev,
                    "lease_inode": a.st_ino,
                    "marker_device": b.st_dev,
                    "marker_inode": b.st_ino,
                    "marker_sha256": hashlib.sha256(m.read_bytes()).hexdigest(),
                }
            )
        self.incident = self.pin("incident.json", {"status": "synthetic_failed"})
        self.evidence = [
            self.pin(f"evidence-{i}.json", {"synthetic": i}) for i in range(3)
        ]
        self.receipt = self.pin(
            "verification.json",
            {
                "schema": "askmill.provider-epoch-settlement.v1",
                "incident_sha256": self.incident["sha256"],
                "provider_epoch_settled": True,
                "original_output": "failed_or_unknown",
                "lease_paths": [x["lease_path"] for x in self.leases],
                "evidence": self.evidence,
            },
        )
        self.verifier = self.pin_raw(
            "verifier.py", b"def verify(receipt, request): return True\n"
        )
        self.req = {
            "schema": "askmill.quarantine-reconciliation.v1",
            "incident": self.incident,
            "verification_receipt": self.receipt,
            "host_verifier": self.verifier,
            "leases": self.leases,
        }
        self.request = self.pin("request.json", self.req)

    def tearDown(self):
        self.tmp.cleanup()

    def pin_raw(self, name, raw):
        p = self.root / name
        p.write_bytes(raw)
        return {"path": str(p), "sha256": hashlib.sha256(raw).hexdigest()}

    def pin(self, name, obj):
        return self.pin_raw(name, json.dumps(obj).encode())

    def markers_exist(self):
        return all(Path(x["lease_path"] + ".unsettled").exists() for x in self.leases)

    def test_success_preserves_custody_and_original_failed_state(self):
        output = self.root / "result"
        r = mod.reconcile(self.request, output)
        self.assertEqual(r["status"], "reconciled")
        self.assertEqual(r["original_output"], "failed_or_unknown")
        self.assertFalse(self.markers_exist())
        for path in r["marker_custody"]:
            self.assertEqual(Path(path).read_bytes(), b"synthetic quarantine")
        self.assertTrue((output / "PREPARED.json").exists())
        self.assertTrue((output / "RECONCILIATION.json").exists())

    def test_refusal_keeps_markers(self):
        self.req["host_verifier"] = self.pin_raw(
            "deny.py", b"def verify(receipt, request): return False\n"
        )
        self.request = self.pin("denied.json", self.req)
        with self.assertRaisesRegex(ValueError, "verifier refused"):
            mod.reconcile(self.request, self.root / "result")
        self.assertTrue(self.markers_exist())

    def test_marker_drift_refuses(self):
        Path(self.leases[0]["lease_path"] + ".unsettled").write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "marker identity"):
            mod.reconcile(self.request, self.root / "result")
        self.assertTrue(self.markers_exist())

    def test_busy_lease_refuses_without_moving(self):
        with open(self.leases[0]["lease_path"], "r+") as locked:
            fcntl.flock(locked, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                mod.reconcile(self.request, self.root / "result")
        self.assertTrue(self.markers_exist())

    def test_partial_move_restores_original(self):
        original = mod.os.rename
        count = [0]

        def fail_second(a, b):
            count[0] += 1
            if count[0] == 2:
                raise OSError("synthetic custody failure")
            return original(a, b)

        with patch.object(mod.os, "rename", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "custody failure"):
                mod.reconcile(self.request, self.root / "result")
        self.assertTrue(self.markers_exist())
        self.assertFalse((self.root / "result" / "RECONCILIATION.json").exists())

    @unittest.skipUnless(hasattr(os, "fork"), "POSIX crash control")
    def test_crash_during_transfer_retains_other_marker_and_custody(self):
        child = os.fork()
        if child == 0:
            original = mod.os.rename
            count = [0]

            def crash_on_second(a, b):
                count[0] += 1
                if count[0] == 2:
                    os._exit(47)
                return original(a, b)

            with patch.object(mod.os, "rename", side_effect=crash_on_second):
                mod.reconcile(self.request, self.root / "result")
            os._exit(48)
        _, status = os.waitpid(child, 0)
        self.assertEqual(os.waitstatus_to_exitcode(status), 47)
        self.assertFalse(Path(self.leases[0]["lease_path"] + ".unsettled").exists())
        self.assertTrue(Path(self.leases[1]["lease_path"] + ".unsettled").exists())
        self.assertTrue((self.root / "result" / "PREPARED.json").exists())
        self.assertTrue((self.root / "result" / "marker-custody-0.bin").exists())
        self.assertFalse((self.root / "result" / "RECONCILIATION.json").exists())

    def test_replaced_lease_after_verification_is_refused(self):
        source = b"import os\ndef verify(receipt, request):\n p=request['leases'][0]['lease_path']\n q=p+'.new'\n open(q,'wb').close()\n os.replace(q,p)\n return True\n"
        self.req["host_verifier"] = self.pin_raw("replace-lease.py", source)
        self.request = self.pin("replace-request.json", self.req)
        with self.assertRaisesRegex(ValueError, "Lease identity changed"):
            mod.reconcile(self.request, self.root / "result")
        self.assertTrue(self.markers_exist())

    def test_verifier_mutation_is_refused(self):
        self.req["host_verifier"] = self.pin_raw(
            "mutator.py",
            b'def verify(receipt, request):\n    receipt["provider_epoch_settled"] = False\n    return True\n',
        )
        self.request = self.pin("mutating-request.json", self.req)
        with self.assertRaisesRegex(ValueError, "mutated"):
            mod.reconcile(self.request, self.root / "result")
        self.assertTrue(self.markers_exist())


if __name__ == "__main__":
    unittest.main()

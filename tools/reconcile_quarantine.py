"""Reconcile exact local quarantine markers using a trusted host verifier.

This tool never starts/stops a provider and never infers settlement. The caller
must authenticate the verifier and its independent provider-epoch evidence.
"""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import types

LIMIT = 4 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_pin(ref):
    if (
        not isinstance(ref, dict)
        or set(ref) != {"path", "sha256"}
        or not Path(ref["path"]).is_absolute()
    ):
        raise ValueError("Expected absolute pinned file reference")
    with Path(ref["path"]).open("rb") as stream:
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT or digest(raw) != ref["sha256"]:
        raise ValueError("Pinned file checksum differs")
    return raw


def parse(raw):
    def pairs(items):
        obj = {}
        for key, value in items:
            if key in obj:
                raise ValueError("Duplicate JSON key")
            obj[key] = value
        return obj

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
    )


def write_new(path, raw):
    with Path(path).open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def save(path, value):
    write_new(
        path,
        (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode(),
    )


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def file_state(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ValueError("Marker is not a regular file")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise ValueError("Marker exceeds limit")
        return {"device": st.st_dev, "inode": st.st_ino, "sha256": digest(raw)}, raw
    finally:
        os.close(fd)


def reconcile(request_ref, output):
    request = parse(read_pin(request_ref))
    if (
        set(request)
        != {"schema", "incident", "verification_receipt", "host_verifier", "leases"}
        or request["schema"] != "askmill.quarantine-reconciliation.v1"
    ):
        raise ValueError("Unsupported reconciliation request")
    incident_raw = read_pin(request["incident"])
    receipt = parse(read_pin(request["verification_receipt"]))
    source = read_pin(request["host_verifier"])
    leases = request["leases"]
    if not isinstance(leases, list) or not 1 <= len(leases) <= 8:
        raise ValueError("Require 1 to 8 exact leases")
    names = []
    for entry in leases:
        if set(entry) != {
            "lease_path",
            "lease_device",
            "lease_inode",
            "marker_device",
            "marker_inode",
            "marker_sha256",
        }:
            raise ValueError("Invalid lease custody descriptor")
        path = entry["lease_path"]
        if not isinstance(path, str) or not Path(path).is_absolute() or path in names:
            raise ValueError("Lease paths must be distinct and absolute")
        names.append(path)
    if (
        receipt.get("schema") != "askmill.provider-epoch-settlement.v1"
        or receipt.get("incident_sha256") != digest(incident_raw)
        or receipt.get("provider_epoch_settled") is not True
        or receipt.get("original_output") != "failed_or_unknown"
        or receipt.get("lease_paths") != names
    ):
        raise ValueError("Verification receipt does not bind this incident and leases")
    evidence = receipt.get("evidence")
    if not isinstance(evidence, list) or len(evidence) < 3:
        raise ValueError("Independent epoch evidence is incomplete")
    for ref in evidence:
        read_pin(ref)
    verifier = types.ModuleType("askmill_host_reconciliation_verifier")
    verifier.__file__ = request["host_verifier"]["path"]
    exec(compile(source, verifier.__file__, "exec"), verifier.__dict__)
    output = Path(output).resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    handles, moved = [], []
    complete = False
    try:
        before = []
        for index, entry in enumerate(leases):
            fd = os.open(entry["lease_path"], os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
            stream = os.fdopen(fd, "r+")
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                st = os.fstat(stream.fileno())
                current = Path(entry["lease_path"]).lstat()
                if (
                    not stat.S_ISREG(st.st_mode)
                    or (st.st_dev, st.st_ino) != (current.st_dev, current.st_ino)
                    or (st.st_dev, st.st_ino)
                    != (entry["lease_device"], entry["lease_inode"])
                ):
                    raise ValueError("Lease identity differs")
            except BaseException:
                stream.close()
                raise
            handles.append(stream)
            marker = Path(entry["lease_path"] + ".unsettled")
            actual, raw = file_state(marker)
            if actual != {
                "device": entry["marker_device"],
                "inode": entry["marker_inode"],
                "sha256": entry["marker_sha256"],
            }:
                raise ValueError("Quarantine marker identity differs")
            if actual["device"] != output.stat().st_dev:
                raise ValueError("Custody requires same filesystem")
            write_new(output / ("marker-before-" + str(index) + ".bin"), raw)
            before.append({"lease_path": entry["lease_path"], "marker": actual})
        verifier_receipt = parse(json.dumps(receipt, allow_nan=False))
        verifier_request = parse(json.dumps(request, allow_nan=False))
        if verifier.verify(verifier_receipt, verifier_request) is not True:
            raise ValueError("Trusted host verifier refused")
        if verifier_receipt != receipt or verifier_request != request:
            raise ValueError("Trusted verifier mutated its inputs")
        # Reopen pins after verifier runs; a changed verifier or proof invalidates it.
        read_pin(request_ref)
        read_pin(request["incident"])
        read_pin(request["verification_receipt"])
        read_pin(request["host_verifier"])
        for ref in evidence:
            read_pin(ref)

        def recheck_leases():
            for handle, entry in zip(handles, leases):
                held = os.fstat(handle.fileno())
                path_state = Path(entry["lease_path"]).lstat()
                if (held.st_dev, held.st_ino) != (
                    path_state.st_dev,
                    path_state.st_ino,
                ) or (held.st_dev, held.st_ino) != (
                    entry["lease_device"],
                    entry["lease_inode"],
                ):
                    raise ValueError("Lease identity changed while held")

        recheck_leases()
        save(
            output / "PREPARED.json",
            {
                "schema": "askmill.reconciliation-prepared.v1",
                "request": request_ref,
                "incident": request["incident"],
                "verification_receipt": request["verification_receipt"],
                "host_verifier": request["host_verifier"],
                "before": before,
                "state": "verified_held_leases_before_custody",
            },
        )
        sync_dir(output)
        for index, entry in enumerate(leases):
            recheck_leases()
            marker = Path(entry["lease_path"] + ".unsettled")
            actual, _ = file_state(marker)
            if actual != before[index]["marker"]:
                raise ValueError("Marker changed before custody transfer")
            custody = output / ("marker-custody-" + str(index) + ".bin")
            os.rename(marker, custody)
            moved.append((marker, custody))
            if file_state(custody)[0] != before[index]["marker"]:
                raise ValueError("Custody identity changed")
            sync_dir(marker.parent)
            sync_dir(output)
        recheck_leases()
        if any(Path(name + ".unsettled").exists() for name in names):
            raise ValueError("Marker reappeared during custody transfer")
        save(
            output / "TRANSFERRED.json",
            {
                "state": "matching_markers_in_custody",
                "paths": [str(c) for _, c in moved],
                "output_state": "failed_or_unknown",
            },
        )
        sync_dir(output)
        complete = True
    finally:
        if not complete:
            for marker, custody in reversed(moved):
                try:
                    os.link(custody, marker)
                    sync_dir(marker.parent)
                except OSError:
                    # Preserve custody snapshots and try remaining restorations;
                    # no successful settlement is emitted after partial failure.
                    pass
        for handle in reversed(handles):
            handle.close()
    if not complete:
        raise ValueError("Reconciliation incomplete")
    result = {
        "schema": "askmill.quarantine-reconciliation-result.v1",
        "status": "reconciled",
        "request": request_ref,
        "verification_receipt": request["verification_receipt"],
        "leases_released": len(handles),
        "marker_custody": [str(c) for _, c in moved],
        "original_output": "failed_or_unknown",
        "provider_stopped_by_tool": False,
        "model_inference": 0,
    }
    save(output / "RECONCILIATION.json", result)
    sync_dir(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = reconcile(
        {"path": args.request, "sha256": args.request_sha256}, args.output
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

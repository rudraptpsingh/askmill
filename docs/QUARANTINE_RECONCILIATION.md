# Quarantine reconciliation CLI v0.1.0

This standalone tool performs controlled marker custody only after an independently authenticated host verifier establishes that the relevant provider execution epoch has settled. It never starts, stops, unloads or contacts a model by itself and does not turn a failed/unknown model response into success. A provider's empty loaded-model list alone is not proof of settlement.

The request `askmill.quarantine-reconciliation.v1` is a pinned JSON file with exactly `schema`, `incident`, `verification_receipt`, `host_verifier`, and `leases`. File refs are absolute `{path,sha256}`. Each lease entry has exactly `lease_path`, `lease_device`, `lease_inode`, `marker_device`, `marker_inode` and `marker_sha256`; its marker must be `<lease_path>.unsettled`. Paths and inode identities must be independently derived from the relevant incident, not guessed or widened. All marker custody destinations must share a filesystem with the markers.

The host-owned `askmill.provider-epoch-settlement.v1` receipt must bind the exact incident file SHA, exact ordered lease paths, at least three independently pinned evidence files, `provider_epoch_settled:true`, and `original_output:'failed_or_unknown'`. Its meaning and freshness are not trusted from those fields alone. The separately authenticated pinned Python verifier is loaded from its exact source bytes and must expose `verify(receipt, request) -> True` only when it independently confirms complete subject identity, no active relevant execution, current provider/process state and the evidence's origin and applicability. Imported verifier dependencies are host-owned trust roots. A fabricated verifier, self-reported receipt, unloaded model list, plausible PID or matching checksum alone is not proof.

```sh
/path/to/python /path/to/installed/tools/reconcile_quarantine.py \
  --request /private/request.json --request-sha256 EXACT_SHA256 \
  --output /private/new-custody-directory
```

It acquires every exact lease nonblocking and rechecks their device/inode identities, captures byte-identical marker copies and validates the pinned receipt/evidence. It calls the host verifier while all leases remain held and all markers remain present, reopens pins and rejects verifier argument mutation, then durably records a PREPARED custody plan. It rechecks each lease and marker before moving markers into the new same-filesystem custody directory, records TRANSFERRED and closes leases before writing RECONCILIATION. A failed or partial move attempts to restore moved markers without overwriting new markers. A crash can interrupt a multi-file transfer; PREPARED, marker copies and custody in the private output directory are retained for explicit operator reconciliation, and no missing final receipt implies success. Do not edit a failed attempt or automatically retry.

This is not a general reset button and does not authenticate source, legal or semantic outcomes. The host must authenticate the verifier implementation and dependency closure, receipt origin, user authority and provider scope, and ensure unrelated processes are not impacted. Reconciliation releases only the named marker files once the verifier has proved the specified epoch settled; the original failed receipt remains immutable.

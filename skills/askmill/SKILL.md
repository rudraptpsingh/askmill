---
name: askmill
description: Run bounded local text or image tasks through an installed AskMill profile, such as explaining a failure log or reading a source crop.
---

Use an existing named profile. Select a receipt store inside the current workspace using global `--store`. Share the host GPU locks through the profile file’s `lease_paths` or explicit global `--lease` options; do not create an unrelated lock to bypass a busy device. Run `askmill doctor --profile NAME` to check configuration without loading weights. Global `--config`, `--store` and `--lease` options go before the subcommand.

For a single call, save the exact prompt to a file and run:
`askmill run --profile NAME --input prompt.txt --max-tokens 512 --timeout 120`.
Use `--image crop.png` for caller-selected images. Supply full instructions in the prompt file; AskMill does not choose a task prompt.
For several related calls, use MCP `run_batch`, CLI `batch` with a Batch JSON file, or reuse a Python `Session` for multiple images to avoid loading a model for every crop.

Select only the diff, log or source image needed for the task. A local model produces candidate findings: reopen its cited lines or source crop, then run the caller's checks before accepting a change.
Exit 3 retains incomplete output; exit 2 reports a failure. Inspect the JSON status. Do not silently change provider when the profile is unavailable.
If cleanup is uncertain, stop that workload and verify the external service settled before clearing the quarantine marker. Do not stop another client's service.

For an existing PDF2Data field-witness request, use `read-fields` and a new output directory. The caller owns rendering, evidence validation and review state; a successful inference is not approval.


For a host configured with AskMill a3 role profiles, choose the task profile
explicitly after checking available names with `askmill list`:
- dev-code: bounded code/log analysis and patch suggestions.
- general: general analysis or source-bound structured questions.
- vision-review: a second visual reading; preserve disagreement.
- pdf-ocr: use the prompt OCR: for literal OCR.
- pdf-table: use Table Recognition: for a table crop.
- pdf-formula: use Formula Recognition: for a formula crop.

Profile names are local configuration, not mandatory model families. Inference
never changes consumer source acceptance. Existing pinned work should retain its
saved profile/revision rather than silently moving to another role.

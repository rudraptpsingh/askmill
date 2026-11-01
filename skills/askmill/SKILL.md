---
name: askmill
description: Run bounded local text or image tasks through an installed AskMill profile, such as explaining a failure log or reading a source crop.
---

Use an existing named profile. Run `askmill doctor --profile NAME` to check configuration without loading weights. Global `--config`, `--store` and `--lease` options go before the subcommand.

For a single call, save the exact prompt to a file and run:
`askmill run --profile NAME --input prompt.txt --max-tokens 512 --timeout 120`.
Use `--image crop.png` for caller-selected images. Supply full instructions in the prompt file; AskMill does not choose a task prompt.
Reuse a Python `Session` for multiple images to avoid loading a model for every crop.

Select only the diff, log or source image needed for the task. A local model produces candidate findings: reopen its cited lines or source crop, then run the caller's checks before accepting a change.
Exit 3 retains incomplete output; exit 2 reports a failure. Inspect the JSON status. Do not silently change provider when the profile is unavailable.
If cleanup is uncertain, stop that workload and verify the external service settled before clearing the quarantine marker. Do not stop another client's service.

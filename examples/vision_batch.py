"""Two synthetic reads in one warm session; requires a configured vision profile."""
import argparse
from pathlib import Path
from askmill import Request
from askmill.profiles import load
from askmill.runner import Session

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--config", required=True)
parser.add_argument("--profile", required=True)
parser.add_argument("--lease", action="append", required=True)
parser.add_argument("--store", required=True)
args = parser.parse_args()
image = str(Path(__file__).with_name("number.png"))
with Session(load(args.config, args.profile), args.store, args.lease) as session:
    for prompt in ("Read the printed number. Digits only.", "What number is shown? Digits only."):
        result = session.run(Request(prompt=prompt, images=[image], max_tokens=32))
        print(result.model_dump_json())
        if result.text.strip() != "42":
            raise SystemExit("Synthetic reading failed; preserve receipt for review")

"""Optional adapter to PDF2Data's published source-image witness import contract."""

import json
from pathlib import Path
import tempfile

from .contract import Request, Source
from .runner import Session


def read_fields(
    profile,
    request_bundle,
    output,
    store,
    lease,
    max_tokens=2048,
    timeout=180.0,
    prompt=None,
):
    from local_vector_batch import field_witness as consumer

    if not 128 <= max_tokens <= 4096 or not 0 < timeout <= 600:
        raise ValueError("Field witness budgets: 128..4096 tokens, 0..600 seconds")
    request_bundle = Path(request_bundle).resolve()
    # This reopens native fields, original PDF and rerendered crop hashes.
    request = consumer.checked_request(request_bundle)
    forbidden = consumer.request_inputs(request_bundle)
    for candidate in (Path(output).resolve(), Path(store).resolve()):
        if any(
            candidate.is_relative_to(p.resolve())
            or p.resolve().is_relative_to(candidate)
            for p in forbidden
        ):
            raise ValueError(
                "Output and receipt store must be outside immutable inputs"
            )
    if Path(output).exists():
        raise ValueError("Use a new witness output")
    request_sha = consumer.file_sha256(request_bundle / "request.json")
    rows, receipts = [], []
    with Session(profile, store, lease) as session:
        for region in request["regions"]:
            image = request_bundle / region["image_file"]
            if consumer.file_sha256(image) != region["image_sha256"]:
                raise ValueError("Source image changed before reading")
            result = session.run(
                Request(
                    prompt=consumer.PROMPT if prompt is None else prompt,
                    images=[str(image)],
                    max_tokens=max_tokens,
                    timeout=float(timeout),
                    sources=[
                        Source(
                            id=region["id"],
                            reference=f"PDF {request['source_pdf_sha256']}, page {region['page']}",
                            content_sha256=region["image_sha256"],
                        )
                    ],
                )
            )
            rows.append(
                {
                    "region_id": region["id"],
                    "image_sha256": region["image_sha256"],
                    "text": result.text,
                    "complete": result.complete,
                }
            )
            receipts.append(
                {
                    "region_id": region["id"],
                    "receipt_id": result.receipt_id,
                    "session_id": result.session_id,
                    "runtime": result.runtime,
                }
            )
    if consumer.canonical(
        consumer.checked_request(request_bundle)
    ) != consumer.canonical(request):
        raise ValueError("Source request changed during reading")
    # Keep execution receipts in retained raw input, not reader identity: retries
    # must not masquerade as independent readers.
    source = {
        "request_sha256": request_sha,
        "regions": rows,
        "execution_receipts": receipts,
        "execution_prompt": consumer.PROMPT if prompt is None else prompt,
    }
    version_key = "mlx-vlm" if profile.provider == "mlx-vlm" else "ollama_version"
    metadata = {
        "reader_id": "askmill",
        "engine": profile.provider,
        "version": result.runtime[version_key],
        "model": profile.model,
        "model_digest": profile.revision,
        "source_text_provided": False,
    }
    with tempfile.TemporaryDirectory(prefix="askmill-fields-") as folder:
        raw, meta = Path(folder) / "reading.json", Path(folder) / "metadata.json"
        raw.write_text(json.dumps(source))
        meta.write_text(json.dumps(metadata))
        summary = consumer.import_reading(request_bundle, raw, meta, output)
    return {
        **summary,
        "status": "completed" if all(r["complete"] for r in rows) else "incomplete",
        "complete": sum(r["complete"] for r in rows),
        "incomplete": sum(not r["complete"] for r in rows),
    }

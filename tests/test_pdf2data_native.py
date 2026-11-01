"""Published PDF2Data integration: actual native extraction and source rerender."""

import json
from pathlib import Path
import pytest

m = pytest.importorskip(
    "local_vector_batch.field_witness", reason="published PDF2Data optional integration"
)


@pytest.fixture
def native_request(tmp_path):
    fitz = pytest.importorskip("fitz")
    pytest.importorskip("pdfplumber")
    from local_vector_batch.legal_l1 import extract_document
    from local_vector_batch.field_rules import extract

    source = tmp_path / "source.pdf"
    pdf = fitz.open()
    page = pdf.new_page(width=300, height=150)
    page.insert_text((30, 70), "Code: 42 END", fontsize=18)
    pdf.save(source)
    pdf.close()
    package = tmp_path / "package"
    extract_document(
        {
            "id": "synthetic",
            "path": str(source),
            "sha256": m.file_sha256(source),
            "family": "generic",
        },
        package,
    )
    rules = tmp_path / "fields.json"
    m.write(
        rules,
        {
            "schema_version": "pdf2data.extraction-rules.v1",
            "fields_schema_version": "pdf2data.configured-fields.v2",
            "id": "code",
            "version": "1",
            "fields": [
                {"id": "code", "type": "text", "pattern": r"Code: (?P<value>42) END"}
            ],
        },
    )
    fields = tmp_path / "native-fields"
    extract(package, rules, fields)
    witness_rules = tmp_path / "witness.json"
    m.write(
        witness_rules,
        {
            "schema_version": m.RULES,
            "id": "code-witness",
            "version": "1",
            "dpi": 144,
            "regions": [{"id": "code", "page": 1, "bbox_pdf_points": [0, 0, 300, 150]}],
            "fields": [
                {
                    "id": "code",
                    "region_id": "code",
                    "native_field_id": "code",
                    "selector": {"kind": "first_line"},
                    "required_tokens": ["42"],
                }
            ],
        },
    )
    request = tmp_path / "request"
    m.prepare(package, fields, witness_rules, request)
    return request, package, fields


@pytest.mark.parametrize("tokens,incomplete", [(2, 0), (128, 1)])
def test_published_native_reader_retains_bindings_and_review_flags(
    mlx_profile, native_request, tmp_path, monkeypatch, tokens, incomplete
):
    from askmill.pdf2data_fields import read_fields

    request, package, fields = native_request
    monkeypatch.setenv("GENERATED_TOKENS", str(tokens))
    before = {
        str(p): m.file_sha256(p)
        for root in (package, fields, request)
        for p in root.rglob("*")
        if p.is_file()
    }
    out = tmp_path / "reading"
    result = read_fields(
        mlx_profile,
        request,
        out,
        tmp_path / "receipts",
        tmp_path / "lock",
        max_tokens=128,
    )
    assert result["incomplete"] == incomplete
    original = m.checked_request(request)
    reading = m.checked_reading(out, request, original)
    assert reading["regions"][0]["state"] == (
        "incomplete" if incomplete else "complete"
    )
    assert reading["attestation"] == "operator_import_not_inference_verified"
    assert all(reading[k] is False for k in m.FLAGS)
    retained = json.loads((out / "external-readings.json").read_text())
    assert retained["execution_receipts"][0]["receipt_id"]
    assert all(m.file_sha256(Path(p)) == value for p, value in before.items())
    # Same model executed twice is still the same reader, never independent votes.
    second = tmp_path / "second"
    read_fields(
        mlx_profile,
        request,
        second,
        tmp_path / "receipts",
        tmp_path / "lock",
        max_tokens=128,
    )
    other = m.checked_reading(second, request, original)
    assert reading["reader_fingerprint"] == other["reader_fingerprint"]


def test_changed_original_and_overlapping_output_rejected_before_model(
    mlx_profile, native_request, tmp_path
):
    from askmill.pdf2data_fields import read_fields

    request, package, fields = native_request
    with pytest.raises(ValueError, match="immutable"):
        read_fields(
            mlx_profile,
            request,
            package / "reading",
            tmp_path / "receipts",
            tmp_path / "lock",
        )
    original = package / "original.pdf"
    original.write_bytes(original.read_bytes() + b"changed")
    with pytest.raises(ValueError):
        read_fields(
            mlx_profile,
            request,
            tmp_path / "reading",
            tmp_path / "receipts",
            tmp_path / "lock",
        )
    assert not (tmp_path / "loads").exists()


def test_native_field_cli_returns_incomplete_exit(
    mlx_profile, native_request, tmp_path, monkeypatch
):
    import subprocess
    import sys

    request, package, fields = native_request
    monkeypatch.setenv("GENERATED_TOKENS", "128")
    config = tmp_path / "profiles.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "askmill.profiles.v1",
                "profiles": {"test": mlx_profile.model_dump()},
            }
        )
    )
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "askmill.cli",
            "--config",
            str(config),
            "--store",
            str(tmp_path / "r"),
            "--lease",
            str(tmp_path / "lock"),
            "read-fields",
            "--profile",
            "test",
            "--request",
            str(request),
            "--output",
            str(tmp_path / "reading"),
            "--max-tokens",
            "128",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 3, (process.stdout, process.stderr)
    value = json.loads(process.stdout)
    assert (
        value["incomplete"] == 1 and value["source_quality_approval_granted"] is False
    )

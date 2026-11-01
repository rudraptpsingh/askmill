"""Optional integration against a separately installed, compatible PDF2Data."""

import hashlib
import json
import subprocess
import sys

import pytest

pytest.importorskip(
    "local_vector_batch.local_ai", reason="PDF2Data named-AI revision is optional"
)


def invoke(args, *, bridge, root):
    command = (
        [
            sys.executable,
            "-m",
            "askmill.pdf2data",
            "--store",
            str(root / "receipts"),
            "--lease",
            str(root / "gpu.lock"),
            "--",
        ]
        if bridge
        else [sys.executable, "-m", "local_vector_batch"]
    )
    return subprocess.run(command + args, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("tokens,expected_exit", [(2, 0), (32, 3)])
def test_existing_cli_outputs_evidence_and_truncation_match(
    mlx_profile, tmp_path, monkeypatch, tokens, expected_exit
):
    monkeypatch.setenv("GENERATED_TOKENS", str(tokens))
    config = tmp_path / "models.json"
    old_profile = {
        "provider": "mlx-vlm",
        "model": mlx_profile.model,
        "python": mlx_profile.python,
        "model_path": mlx_profile.model_path,
    }
    config.write_text(
        json.dumps(
            {
                "schema_version": "pdf2data.local-models.v1",
                "models": {"qwen": old_profile},
            }
        )
    )
    before = config.read_bytes()
    images = []
    for i in range(2):
        image = tmp_path / f"crop{i}.png"
        image.write_bytes(b"synthetic crop bytes:" + str(i).encode())
        images += ["--image", str(image)]
    base = [
        "ai",
        "run",
        "qwen",
        "--config",
        str(config),
        "--prompt",
        "Read exactly: ₹ 42; include every qualifier.",
        "--max-tokens",
        "32",
        "--json",
    ] + images
    for bridge in (False, True):
        out = tmp_path / ("shared" if bridge else "original")
        process = invoke(base + ["--output", str(out)], bridge=bridge, root=tmp_path)
        assert process.returncode == expected_exit, (process.stdout, process.stderr)
        receipt = json.loads((out / "receipt.json").read_text())
        response = json.loads((out / "response.json").read_text())
        assert (
            not receipt["source_quality_changed"]
            and not receipt["publication_eligible"]
        )
        assert receipt["complete"] == (tokens < 32)
        assert (out / "output.txt").read_text() == "42"
        assert (
            receipt["request_sha256"]
            == hashlib.sha256((out / "request.json").read_bytes()).hexdigest()
        )
        assert (
            receipt["response_sha256"]
            == hashlib.sha256((out / "response.json").read_bytes()).hexdigest()
        )
        assert (
            response["device"] == "gpu" and response["peak_device_memory_bytes"] == 100
        )
    assert (tmp_path / "original/request.json").read_bytes() == (
        tmp_path / "shared/request.json"
    ).read_bytes()
    assert config.read_bytes() == before


def test_existing_add_list_probe_and_original_binding_restored(mlx_profile, tmp_path):
    config = tmp_path / "models.json"
    args = [
        "ai",
        "add",
        "qwen",
        "--provider",
        "mlx-vlm",
        "--model",
        mlx_profile.model,
        "--python",
        mlx_profile.python,
        "--model-path",
        mlx_profile.model_path,
        "--config",
        str(config),
        "--json",
    ]
    assert invoke(args, bridge=True, root=tmp_path).returncode == 0
    before = config.read_bytes()
    for command in (["ai", "list"], ["ai", "probe", "qwen"]):
        old = invoke(
            command + ["--config", str(config), "--json"], bridge=False, root=tmp_path
        )
        new = invoke(
            command + ["--config", str(config), "--json"], bridge=True, root=tmp_path
        )
        assert old.returncode == new.returncode == 0
        assert json.loads(old.stdout) == json.loads(new.stdout)
    assert config.read_bytes() == before
    from askmill.pdf2data import main
    from local_vector_batch import local_ai

    original = local_ai.Session
    assert (
        main(
            [
                "--store",
                str(tmp_path / "r"),
                "--lease",
                str(tmp_path / "lock"),
                "--",
                "ai",
                "list",
                "--config",
                str(config),
                "--json",
            ]
        )
        == 0
    )
    assert local_ai.Session is original


def test_two_crop_session_preserves_prompt_order_budget_and_load_count(
    mlx_profile, tmp_path, monkeypatch
):
    log = tmp_path / "generation.jsonl"
    monkeypatch.setenv("GENERATION_LOG", str(log))
    profile = {
        "provider": "mlx-vlm",
        "model": mlx_profile.model,
        "python": mlx_profile.python,
        "model_path": mlx_profile.model_path,
    }
    images = []
    for i in range(2):
        path = tmp_path / f"crop{i}.png"
        path.write_bytes(bytes([i]))
        images.append(str(path))
    program = """
import json,sys
from local_vector_batch.local_ai import Session as Original
from askmill.pdf2data import MLXSession
profile,images,store,lease=json.loads(sys.argv[1])
for session in (Original(profile), MLXSession(profile,store=store,lease=lease)):
    try:
        for i,image in enumerate(images):
            result=session.generate('prompt '+str(i),[image],32+i,10)
            assert result['complete'] and result['text']=='42'
    finally:session.close()
"""
    data = [profile, images, str(tmp_path / "r"), str(tmp_path / "lock")]
    process = subprocess.run(
        [sys.executable, "-c", program, json.dumps(data)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert process.returncode == 0, process.stderr
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert rows[:2] == rows[2:]
    assert [row["prompt"] for row in rows[:2]] == ["prompt 0", "prompt 1"]
    assert [row["max_tokens"] for row in rows[:2]] == [32, 33]
    assert (tmp_path / "loads").read_text().splitlines() == ["load", "load"]


def test_formula_review_reopens_sources_and_keeps_holds(mlx_profile, tmp_path):
    fitz = pytest.importorskip("fitz")
    pdfium = pytest.importorskip("pypdfium2")
    pytest.importorskip("filelock")
    from local_vector_batch.formula_audit import SOURCE_FILES, source_data
    from local_vector_batch.formula_observations import extract_formulas
    from local_vector_batch.legal_l1 import structure_document
    from local_vector_batch.hashing import file_sha256

    def write(path, data):
        path.write_text(json.dumps(data))

    package = tmp_path / "package"
    (package / "extraction").mkdir(parents=True)
    source = package / "original.pdf"
    document = fitz.open()
    texts = ["2 + 3 = 5", "7 - 2 = 5"]
    for text in texts:
        page = document.new_page(width=300, height=150)
        page.insert_text((30, 60), text, fontsize=22)
    document.save(source)
    document.close()
    sha = file_sha256(source)
    pages = [
        {
            "page": i + 1,
            "text": text,
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
        for i, text in enumerate(texts)
    ]
    (package / "extraction/pages.jsonl").write_text(
        "".join(json.dumps(p) + "\n" for p in pages)
    )
    (package / "layout.jsonl").write_text("")
    write(package / "extraction/tables.json", [])
    write(package / "structure.json", structure_document(pages, sha, "generic"))
    write(
        package / "quality.json",
        {"results": [{"page": i + 1, "outcome": "needs_review"} for i in range(2)]},
    )
    before = {name: file_sha256(package / name) for name in SOURCE_FILES}
    audit_root = tmp_path / "audit"
    audit_root.mkdir()
    views = []
    with pdfium.PdfDocument(str(source)) as original:
        for i in range(2):
            page = original[i]
            bitmap = page.render(scale=2)
            image = bitmap.to_pil()
            path = audit_root / f"page{i}.png"
            image.save(path)
            image.close()
            bitmap.close()
            page.close()
            views.append(
                {
                    "page": i + 1,
                    "path": str(path),
                    "sha256": file_sha256(path),
                    "dpi": 144,
                }
            )
    formulas = audit_root / "formulas.json"
    write(formulas, extract_formulas(source_data(package, sha)))
    audit = audit_root / "audit.json"
    write(
        audit,
        {
            "documents": [
                {
                    "source_id": "synthetic",
                    "source_pdf": str(source),
                    "source_pdf_sha256": sha,
                    "package": str(package),
                    "source_views": views,
                    "source_files": before,
                    "formula_artifact": str(formulas),
                    "formula_artifact_sha256": file_sha256(formulas),
                }
            ]
        },
    )
    selection = tmp_path / "selection.json"
    write(selection, [{"source_id": "synthetic", "pages": [1, 2]}])
    config = tmp_path / "models.json"
    profile = {
        "provider": "mlx-vlm",
        "model": mlx_profile.model,
        "python": mlx_profile.python,
        "model_path": mlx_profile.model_path,
    }
    write(
        config,
        {"schema_version": "pdf2data.local-models.v1", "models": {"qwen": profile}},
    )
    for bridge in (False, True):
        out = tmp_path / ("shared" if bridge else "old")
        args = [
            "pdf-formulas",
            "review-ai",
            "--model",
            "qwen",
            "--config",
            str(config),
            "--audit",
            str(audit),
            "--selection",
            str(selection),
            "--output",
            str(out),
            "--max-tokens",
            "256",
            "--json",
        ]
        result = invoke(args, bridge=bridge, root=tmp_path)
        assert result.returncode == 0, (result.stdout, result.stderr)
        record = json.loads((out / "review.json").read_text())
        assert (
            not record["source_quality_changed"] and not record["publication_eligible"]
        )
        assert len(record["results"]) == 2
        for row in record["results"]:
            assert (
                not row["interpretation_verified"] and not row["source_quality_changed"]
            )
            assert (
                row["raw"] == "42" and row["parse_error"]
            )  # bad model reading remains a candidate
            assert row["device"] == "gpu" and row["peak_device_memory_bytes"] == 100
        assert {name: file_sha256(package / name) for name in SOURCE_FILES} == before
    # Both original and shared paths loaded one model for their two-page reviews.
    assert (tmp_path / "loads").read_text().splitlines() == ["load", "load"]

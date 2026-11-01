"""Host-local profile files. No silent conversion or config writes."""
import hashlib
import json
from pathlib import Path
from .contract import Profile
from .runner import RunError, digest


def model_revision(path):
    root = Path(path)
    entries = []
    for item in sorted(root.rglob("*")):
        if item.is_file() and not item.name.startswith("."):
            sha = hashlib.sha256()
            with item.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    sha.update(chunk)
            entries.append([item.relative_to(root).as_posix(), sha.hexdigest()])
    if not entries:
        raise ValueError("Cached model directory is empty")
    return "sha256:" + digest(entries)


def load(path, name):
    data = json.loads(Path(path).read_text())
    if data.get("schema_version") != "askmill.profiles.v1":
        raise ValueError("Unsupported profile file")
    if name not in data["profiles"]:
        raise RunError("profile_missing", "Unknown named profile")
    return Profile.model_validate(data["profiles"][name])


def from_pdf2data(data, revision):
    """Return a converted profile; the caller chooses where to save it."""
    if data["provider"] != "mlx-vlm":
        raise RunError("unsupported", "HTTP profile migration requires an independently verified model identity")
    return Profile(provider="mlx-vlm", model=data["model"], revision=revision,
                   python=data["python"], model_path=data["model_path"],
                   capabilities=["text", "vision"], ownership="worker")

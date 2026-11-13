"""Verify CSV bytes against their import manifest and report the actual inputs."""

import hashlib
import json
from pathlib import Path

from .contracts import FILES


def source_manifest(raw_dir: Path) -> dict:
    """Fail on changed/missing imported CSVs; label untracked manual input explicitly."""
    hashes = {}
    for filename in FILES.values():
        path = raw_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"{path}: run python -m src.download_data first")
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        hashes[filename] = digest.hexdigest()
    path = raw_dir / "manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        expected = manifest.get("files_sha256", {})
        changed = [
            name for name, value in hashes.items() if expected.get(name) != value
        ]
        if changed:
            raise ValueError(
                f"Source SHA-256 mismatch: {changed}. Restore or re-import original CSVs."
            )
        manifest = {**manifest, "integrity": "verified against data/raw/manifest.json"}
    else:
        manifest = {
            "source": "manual CSV input; origin and license unverified",
            "integrity": "no import manifest; actual file hashes recorded",
            "license": "unverified",
        }
    return {**manifest, "files_sha256": hashes}

"""Download original Kaggle archive, or import a manually downloaded ZIP.

No credentials required by the public endpoint at the time of development.
HTML/login responses fail explicitly; local import is always supported.
"""

import argparse
import hashlib
import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from .config import RAW
from .contracts import FILES

URL = "https://www.kaggle.com/api/v1/datasets/download/olistbr/brazilian-ecommerce"
SOURCE = "https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce"


def extract_archive(archive: Path, destination: Path, source: str) -> dict:
    """Stage required members before publishing. Never extract arbitrary ZIP paths."""
    destination.mkdir(parents=True, exist_ok=True)
    with (
        zipfile.ZipFile(archive) as z,
        tempfile.TemporaryDirectory(dir=destination) as tmp,
    ):
        members = z.namelist()
        for required in FILES.values():
            if sum(Path(n).name == required for n in members) > 1:
                raise ValueError(
                    f"Archive contains ambiguous duplicate filename: {required}"
                )
        by_name = {Path(n).name: n for n in members}
        missing = set(FILES.values()) - set(by_name)
        if missing:
            raise ValueError(f"Archive missing files: {sorted(missing)}")
        for name in FILES.values():
            if z.getinfo(by_name[name]).file_size > 500_000_000:
                raise ValueError(f"Unexpectedly large member: {name}")
            Path(tmp, name).write_bytes(z.read(by_name[name]))
        hashes = {
            n: hashlib.sha256(Path(tmp, n).read_bytes()).hexdigest()
            for n in FILES.values()
        }
        for n in FILES.values():
            Path(tmp, n).replace(destination / n)
    manifest = {
        "source": source,
        "dataset_page": SOURCE,
        "license": "CC BY-NC-SA 4.0",
        "downloaded_utc": datetime.now(timezone.utc).isoformat(),
        "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "files_sha256": hashes,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def download(destination: Path = RAW, archive: Path | None = None) -> dict:
    """Download to a temporary file; do not leave a partial CSV on HTTP failure."""
    if archive is not None:
        return extract_archive(archive, destination, "manual ZIP from " + SOURCE)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "olist.zip"
        with requests.get(URL, stream=True, timeout=(20, 180)) as response:
            response.raise_for_status()
            with path.open("wb") as f:
                for chunk in response.iter_content(1024 * 1024):
                    f.write(chunk)
        if not zipfile.is_zipfile(path):
            raise ValueError(
                "Kaggle returned a non-ZIP response. Download manually and use --archive FILE.zip"
            )
        return extract_archive(path, destination, URL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    download(archive=args.archive)
    print("Original CSVs ready in data/raw; SHA-256 saved in manifest.json")

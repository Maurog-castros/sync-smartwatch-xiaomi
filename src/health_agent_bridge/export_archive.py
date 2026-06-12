from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path


def export_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pick_xml_from_zip(archive: zipfile.ZipFile) -> str:
    candidates = [
        name
        for name in archive.namelist()
        if name.lower().endswith(".xml")
        and "cda" not in name.lower()
        and not name.endswith("/")
    ]
    if not candidates:
        raise FileNotFoundError("No XML file found inside Apple Health export zip")

    preferred = [
        name
        for name in candidates
        if name.endswith("export.xml") or name.endswith("exportar.xml")
    ]
    if preferred:
        return sorted(preferred, key=len)[0]
    return sorted(candidates, key=len)[0]


def resolve_export_xml(export_path: Path, extract_dir: Path | None = None) -> Path:
    if export_path.suffix.lower() == ".xml":
        return export_path

    if export_path.suffix.lower() != ".zip":
        raise ValueError(f"Unsupported export format: {export_path}")

    target_dir = extract_dir or export_path.parent / export_path.stem
    target_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(export_path) as archive:
        member = _pick_xml_from_zip(archive)
        archive.extract(member, target_dir)
        extracted = target_dir / member
        if not extracted.exists():
            raise FileNotFoundError(f"Extracted XML not found: {extracted}")
        return extracted


def newest_export_in(storage_dir: Path) -> Path | None:
    candidates = sorted(
        [
            *storage_dir.glob("*.zip"),
            *storage_dir.glob("**/*.zip"),
        ],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in candidates:
        if path.is_file():
            return path
    return None

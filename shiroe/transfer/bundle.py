"""Digest-checked artifact bundles."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import tarfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ARTIFACT_BUNDLE_SCHEMA = "shiroe.artifact-bundle/v1"


class BundleError(ValueError):
    """Raised when an artifact bundle is unsafe or corrupt."""


@dataclass(frozen=True)
class ArtifactBundleManifest:
    schema: str
    files: tuple[dict[str, Any], ...]
    manifest_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "files": list(self.files),
            "manifest_digest": self.manifest_digest,
        }


def create_artifact_bundle(source_dir: Path | str, bundle_path: Path | str) -> ArtifactBundleManifest:
    source = Path(source_dir)
    target = Path(bundle_path)
    entries = _source_entries(source)
    manifest_body = {
        "schema": ARTIFACT_BUNDLE_SCHEMA,
        "files": [entry for entry, _path in entries],
    }
    manifest_bytes = _canonical_json(manifest_body)
    manifest = ArtifactBundleManifest(
        schema=ARTIFACT_BUNDLE_SCHEMA,
        files=tuple(manifest_body["files"]),
        manifest_digest=_digest_bytes(manifest_bytes),
    )
    with tarfile.open(target, "w") as tf:
        _add_bytes(tf, "manifest.json", manifest_bytes)
        for entry, path in entries:
            info = tarfile.TarInfo(f"files/{entry['path']}")
            info.size = entry["size"]
            info.mode = stat.S_IMODE(path.stat().st_mode)
            with path.open("rb") as handle:
                tf.addfile(info, handle)
    return manifest


def extract_artifact_bundle(bundle_path: Path | str, destination: Path | str) -> ArtifactBundleManifest:
    bundle = Path(bundle_path)
    dest = Path(destination)
    parent = dest.parent
    tmp = parent / f".{dest.name}.tmp.{uuid.uuid4().hex}"
    backup = parent / f".{dest.name}.old.{uuid.uuid4().hex}"
    try:
        manifest, payloads = _read_bundle(bundle)
        tmp.mkdir(parents=True)
        for entry in manifest.files:
            rel = _validate_relative_path(str(entry["path"]))
            payload = payloads.get(rel)
            if payload is None:
                raise BundleError(f"missing artifact payload for {rel}")
            expected_size = int(entry["size"])
            if len(payload) != expected_size:
                raise BundleError(f"artifact size mismatch for {rel}")
            if _digest_bytes(payload) != entry["sha256"]:
                raise BundleError(f"artifact hash mismatch for {rel}")
            path = tmp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)

        if dest.exists():
            os.replace(dest, backup)
        os.replace(tmp, dest)
        if backup.exists():
            shutil.rmtree(backup)
        return manifest
    except Exception:
        if tmp.exists():
            shutil.rmtree(tmp)
        if backup.exists() and not dest.exists():
            os.replace(backup, dest)
        elif backup.exists():
            shutil.rmtree(backup)
        raise


def _source_entries(source: Path) -> list[tuple[dict[str, Any], Path]]:
    if not source.is_dir():
        raise BundleError("artifact source must be a directory")
    entries: list[tuple[dict[str, Any], Path]] = []
    seen: set[str] = set()
    for path in sorted(p for p in source.rglob("*") if p.is_file() or p.is_symlink()):
        rel = path.relative_to(source).as_posix()
        rel = _validate_relative_path(rel)
        if rel in seen:
            raise BundleError(f"duplicate artifact path {rel}")
        seen.add(rel)
        if path.is_symlink():
            raise BundleError(f"artifact path {rel} is a symlink")
        st = path.stat()
        if not stat.S_ISREG(st.st_mode):
            raise BundleError(f"artifact path {rel} is not a regular file")
        if st.st_nlink > 1:
            raise BundleError(f"artifact path {rel} is a hardlink")
        data = path.read_bytes()
        entries.append(
            (
                {
                    "path": rel,
                    "sha256": _digest_bytes(data),
                    "size": len(data),
                },
                path,
            )
        )
    return entries


def _read_bundle(bundle: Path) -> tuple[ArtifactBundleManifest, dict[str, bytes]]:
    with tarfile.open(bundle, "r") as tf:
        members = tf.getmembers()
        names: set[str] = set()
        payloads: dict[str, bytes] = {}
        manifest_bytes: bytes | None = None
        for member in members:
            if member.name in names:
                raise BundleError(f"duplicate bundle member {member.name}")
            names.add(member.name)
            if member.name == "manifest.json":
                if not member.isfile():
                    raise BundleError("manifest.json must be a regular file")
                manifest_bytes = _read_member(tf, member)
                continue
            if not member.name.startswith("files/"):
                raise BundleError(f"unexpected bundle member {member.name}")
            if not member.isfile() or member.issym() or member.islnk() or member.isdev():
                raise BundleError(f"artifact member {member.name} is not a regular file")
            rel = _validate_relative_path(member.name[len("files/"):])
            payloads[rel] = _read_member(tf, member)
        if manifest_bytes is None:
            raise BundleError("missing artifact manifest")
    manifest = _manifest_from_bytes(manifest_bytes)
    manifest_paths = {str(entry["path"]) for entry in manifest.files}
    if set(payloads) != manifest_paths:
        raise BundleError("artifact bundle payload set does not match manifest")
    return manifest, payloads


def _manifest_from_bytes(data: bytes) -> ArtifactBundleManifest:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError("artifact manifest is invalid JSON") from exc
    if parsed.get("schema") != ARTIFACT_BUNDLE_SCHEMA:
        raise BundleError("artifact manifest has wrong schema")
    files = parsed.get("files")
    if not isinstance(files, list):
        raise BundleError("artifact manifest files must be a list")
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for entry in files:
        if not isinstance(entry, dict):
            raise BundleError("artifact manifest file entry must be an object")
        rel = _validate_relative_path(str(entry.get("path") or ""))
        if rel in seen:
            raise BundleError(f"duplicate artifact path {rel}")
        seen.add(rel)
        digest = str(entry.get("sha256") or "")
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise BundleError(f"artifact {rel} missing sha256")
        size = entry.get("size")
        if not isinstance(size, int) or size < 0:
            raise BundleError(f"artifact {rel} has invalid size")
        normalized.append({"path": rel, "sha256": digest, "size": size})
    canonical = _canonical_json({"schema": ARTIFACT_BUNDLE_SCHEMA, "files": normalized})
    return ArtifactBundleManifest(
        schema=ARTIFACT_BUNDLE_SCHEMA,
        files=tuple(normalized),
        manifest_digest=_digest_bytes(canonical),
    )


def _validate_relative_path(path: str) -> str:
    rel = Path(path)
    if not path or rel.is_absolute() or ".." in rel.parts:
        raise BundleError("artifact paths must be relative and stay inside the bundle")
    normalized = rel.as_posix()
    if normalized.startswith("./") or normalized == ".":
        raise BundleError("artifact paths must be relative file paths")
    return normalized


def _read_member(tf: tarfile.TarFile, member: tarfile.TarInfo) -> bytes:
    handle = tf.extractfile(member)
    if handle is None:
        raise BundleError(f"could not read bundle member {member.name}")
    return handle.read()


def _add_bytes(tf: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    tf.addfile(info, io.BytesIO(data))


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()

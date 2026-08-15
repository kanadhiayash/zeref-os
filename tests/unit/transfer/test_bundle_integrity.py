from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from shiroe.transfer.bundle import BundleError, create_artifact_bundle, extract_artifact_bundle


def test_artifact_bundle_round_trips_files_atomically(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "stdout.txt").write_text("ok\n", encoding="utf-8")
    nested = source / "nested"
    nested.mkdir()
    (nested / "receipt.json").write_text('{"ok":true}\n', encoding="utf-8")
    bundle = tmp_path / "bundle.tar"
    destination = tmp_path / "dest"
    destination.mkdir()
    (destination / "old.txt").write_text("old\n", encoding="utf-8")

    manifest = create_artifact_bundle(source, bundle)
    extract_artifact_bundle(bundle, destination)

    assert manifest.manifest_digest.startswith("sha256:")
    assert not (destination / "old.txt").exists()
    assert (destination / "stdout.txt").read_text(encoding="utf-8") == "ok\n"
    assert (destination / "nested" / "receipt.json").read_text(encoding="utf-8") == '{"ok":true}\n'


def test_artifact_bundle_rejects_source_symlink(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "target.txt").write_text("target", encoding="utf-8")
    (source / "link.txt").symlink_to(source / "target.txt")

    with pytest.raises(BundleError, match="symlink"):
        create_artifact_bundle(source, tmp_path / "bundle.tar")


def test_artifact_bundle_rejects_traversal_and_leaves_destination_unchanged(tmp_path: Path) -> None:
    bundle = tmp_path / "bundle.tar"
    destination = tmp_path / "dest"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep\n", encoding="utf-8")
    payload = b"pwned"
    manifest = {
        "schema": "shiroe.artifact-bundle/v1",
        "files": [
            {
                "path": "../pwned.txt",
                "sha256": "sha256:" + ("0" * 64),
                "size": len(payload),
            }
        ],
    }
    with tarfile.open(bundle, "w") as tf:
        manifest_bytes = json.dumps(manifest, sort_keys=True).encode("utf-8")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(manifest_bytes)
        tf.addfile(info, io.BytesIO(manifest_bytes))
        bad = tarfile.TarInfo("files/../pwned.txt")
        bad.size = len(payload)
        tf.addfile(bad, io.BytesIO(payload))

    with pytest.raises(BundleError, match="relative"):
        extract_artifact_bundle(bundle, destination)

    assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep\n"
    assert not (tmp_path / "pwned.txt").exists()


def test_artifact_bundle_rejects_hash_mismatch(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "result.txt").write_text("ok", encoding="utf-8")
    bundle = tmp_path / "bundle.tar"
    create_artifact_bundle(source, bundle)

    # Rewrite the payload member while preserving the original manifest.
    original = {}
    with tarfile.open(bundle, "r") as tf:
        original["manifest"] = tf.extractfile("manifest.json").read()
    with tarfile.open(bundle, "w") as tf:
        info = tarfile.TarInfo("manifest.json")
        info.size = len(original["manifest"])
        tf.addfile(info, io.BytesIO(original["manifest"]))
        payload = b"NO"
        data_info = tarfile.TarInfo("files/result.txt")
        data_info.size = len(payload)
        tf.addfile(data_info, io.BytesIO(payload))

    with pytest.raises(BundleError, match="hash"):
        extract_artifact_bundle(bundle, tmp_path / "dest")

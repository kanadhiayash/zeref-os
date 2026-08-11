from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_generic_context_and_codec_runtime_removed():
    assert not (ROOT / "shiroe/context").exists()
    assert not (ROOT / "shiroe/codecs").exists()

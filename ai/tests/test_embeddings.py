from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

from silki_ai.embeddings import SentenceTransformerEmbedder

ROOT = Path(__file__).resolve().parents[1]


def test_embedding_model_is_explicitly_loaded_on_cpu(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []
    module = ModuleType("sentence_transformers")

    def fake_sentence_transformer(model_name: str, *, device: str) -> object:
        calls.append((model_name, device))
        return object()

    module.SentenceTransformer = fake_sentence_transformer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    embedder = SentenceTransformerEmbedder("test-model")

    embedder._load_model()

    assert calls == [("test-model", "cpu")]


def test_lockfile_contains_no_accelerator_runtime_packages() -> None:
    lockfile = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert 'registry = "https://download.pytorch.org/whl/cpu"' in lockfile
    for forbidden_name in ('name = "cuda-', 'name = "nvidia-', 'name = "triton"'):
        assert forbidden_name not in lockfile

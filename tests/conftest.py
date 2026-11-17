"""Mantém os relatórios gerados pelos testes longe da pasta `data` de verdade."""

import pytest


@pytest.fixture(autouse=True)
def isolated_review_directory(tmp_path, monkeypatch):
    monkeypatch.setattr("src.import_ea.REVIEW_DIRECTORY", tmp_path / "review")

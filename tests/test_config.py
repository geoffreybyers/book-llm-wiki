# tests/test_config.py
import textwrap
from pathlib import Path

from book_summarizer.config import load_config


def test_load_config_from_single_file(tmp_path: Path):
    cfg_file = tmp_path / "books.yaml"
    cfg_file.write_text(textwrap.dedent("""
        defaults:
          vault_path: ~/obsidian/book summaries
          max_parallel_chapters: 5
          default_lens: general
        lenses:
          general: |
            Standard lens text.
    """))
    cfg = load_config(cfg_file)
    assert cfg.vault_path.name == "book summaries"
    assert cfg.max_parallel_chapters == 5
    assert cfg.default_lens == "general"
    assert "Standard lens text" in cfg.lenses["general"]


def test_local_yaml_overrides_main(tmp_path: Path):
    main = tmp_path / "books.yaml"
    local = tmp_path / "books.local.yaml"
    main.write_text(textwrap.dedent("""
        defaults:
          vault_path: /should/be/overridden
          max_parallel_chapters: 5
          default_lens: general
        lenses: {general: "main"}
    """))
    local.write_text(textwrap.dedent("""
        defaults:
          vault_path: /local/path
          max_parallel_chapters: 3
    """))
    cfg = load_config(main, local_path=local)
    assert str(cfg.vault_path) == "/local/path"
    assert cfg.max_parallel_chapters == 3
    assert cfg.default_lens == "general"  # untouched
    assert cfg.lenses["general"] == "main"  # untouched


def test_missing_config_raises(tmp_path: Path):
    import pytest
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")

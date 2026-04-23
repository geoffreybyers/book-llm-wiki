"""Load books.yaml and merge books.local.yaml overrides."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    vault_path: Path
    chapter_model: str = "claude-opus-4-7"
    synthesis_model: str = "claude-opus-4-7"
    max_parallel_chapters: int = 5
    min_chapters_for_map_reduce: int = 3
    max_chapter_share_of_book: float = 0.60
    max_chapters: int = 80
    default_lens: str = "general"
    lenses: dict[str, str] = field(default_factory=dict)
    overrides: dict[str, dict] = field(default_factory=dict)


def _deep_merge(base: dict, overlay: dict) -> dict:
    result = dict(base)
    for key, val in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_config(path: Path, local_path: Path | None = None) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")

    with path.open() as fh:
        data = yaml.safe_load(fh) or {}

    if local_path is None:
        local_path = path.parent / "books.local.yaml"
    if local_path.exists():
        with local_path.open() as fh:
            local = yaml.safe_load(fh) or {}
        data = _deep_merge(data, local)

    defaults = data.get("defaults", {})
    vault_path = Path(defaults.get("vault_path", "~/obsidian/book summaries")).expanduser()

    return Config(
        vault_path=vault_path,
        chapter_model=defaults.get("chapter_model", "claude-opus-4-7"),
        synthesis_model=defaults.get("synthesis_model", "claude-opus-4-7"),
        max_parallel_chapters=defaults.get("max_parallel_chapters", 5),
        min_chapters_for_map_reduce=defaults.get("min_chapters_for_map_reduce", 3),
        max_chapter_share_of_book=defaults.get("max_chapter_share_of_book", 0.60),
        max_chapters=defaults.get("max_chapters", 80),
        default_lens=defaults.get("default_lens", "general"),
        lenses=data.get("lenses", {}),
        overrides=data.get("overrides", {}),
    )

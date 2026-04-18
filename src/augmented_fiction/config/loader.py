import json
from pathlib import Path

from augmented_fiction.config.schema import ProjectConfig


def load_config(project_path: Path) -> ProjectConfig:
    config_file = project_path / "config.json"
    if not config_file.exists():
        raise FileNotFoundError(f"No config.json in {project_path}")
    return ProjectConfig.model_validate(json.loads(config_file.read_text()))


def save_config(config: ProjectConfig, project_path: Path) -> None:
    config_file = project_path / "config.json"
    config_file.write_text(config.model_dump_json(indent=2))

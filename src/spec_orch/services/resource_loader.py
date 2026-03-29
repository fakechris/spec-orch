from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any


def load_json_resource(
    *,
    resource_name: str,
    package: str = "spec_orch.resources",
    repo_root: Path | None = None,
    override_subdir: str = "tests/fixtures",
) -> dict[str, Any]:
    if repo_root is not None:
        override_path = Path(repo_root) / override_subdir / resource_name
        if override_path.exists():
            data = json.loads(override_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"Override resource {resource_name} must contain a JSON object")
            return data

    data = json.loads(resources.files(package).joinpath(resource_name).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Packaged resource {resource_name} must contain a JSON object")
    return data

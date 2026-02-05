from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from pathlib import Path


class ModuleIssueCode(str, Enum):
    MISSING_INIT_YAML = "missing_init_yaml"  # Legacy: kept for compatibility, also used for missing pyproject.toml
    MISSING_PYPROJECT = "missing_pyproject"  # New: explicitly for pyproject.toml
    MISSING_VERSION = "missing_version"
    MISSING_REQUIREMENTS = "missing_requirements"
    # Layer validation codes
    MISSING_LAYER = "missing_layer"
    INVALID_LAYER = "invalid_layer"
    INVALID_LAYER_FOR_PATH = "invalid_layer_for_path"  # Layer not valid for this path/folder
    # Doctor-specific codes
    ORPHANED_INIT_YAML = "orphaned_init_yaml"  # Has both init.yaml and pyproject.toml
    MISSING_ADHD_SECTION = "missing_adhd_section"  # pyproject.toml missing [tool.adhd]
    INVALID_TOML = "invalid_toml"  # pyproject.toml is not valid TOML
    # Workspace validation codes
    MISSING_WORKSPACE_SOURCE = "missing_workspace_source"  # Module not in [tool.uv.sources]
    MISSING_WORKSPACE_MEMBER = "missing_workspace_member"  # Module folder not matched by members glob



# Map keys to issue codes for simple presence validation
# NOTE: repo_url is intentionally NOT required - internal modules don't need GitHub URLs
# NOTE: type is no longer required - it's inferred from folder path
REQUIRED_INIT_KEYS: Dict[str, ModuleIssueCode] = {
    "version": ModuleIssueCode.MISSING_VERSION,
}

# Message templates per issue code (use {key} placeholder)
ISSUE_MESSAGES: Dict[ModuleIssueCode, str] = {
    ModuleIssueCode.MISSING_INIT_YAML: (
        "Module is missing configuration file. Please add a pyproject.toml with [tool.adhd] section."
    ),
    ModuleIssueCode.MISSING_PYPROJECT: (
        "Module is missing pyproject.toml. Please add a pyproject.toml with [tool.adhd] section."
    ),
    ModuleIssueCode.MISSING_VERSION: (
        "Module is missing '{key}' in pyproject.toml. Specify a semantic version such as '0.0.1' under [project].version."
    ),
    ModuleIssueCode.MISSING_REQUIREMENTS: (
        "Module is missing '{key}' in pyproject.toml. Include a list (can be empty) of dependencies under [project].dependencies."
    ),
    # Layer validation messages
    ModuleIssueCode.MISSING_LAYER: (
        "Module is missing 'layer' in pyproject.toml. Set the module's layer (foundation, runtime, dev) under [tool.adhd].layer."
    ),
    ModuleIssueCode.INVALID_LAYER: (
        "Module has invalid layer value '{key}'. Valid values are: foundation, runtime, dev."
    ),
    ModuleIssueCode.INVALID_LAYER_FOR_PATH: (
        "Module has invalid layer for its location. '{key}' layer is not valid for this path. Check folder-layer constraints."
    ),
    # Doctor-specific messages
    ModuleIssueCode.ORPHANED_INIT_YAML: (
        "Module has orphaned init.yaml (deprecated). Both init.yaml and pyproject.toml exist. Run 'adhd migrate --module {key}' to remove init.yaml."
    ),
    ModuleIssueCode.MISSING_ADHD_SECTION: (
        "Module pyproject.toml is missing [tool.adhd] section. Add type configuration under [tool.adhd]."
    ),
    ModuleIssueCode.INVALID_TOML: (
        "Module pyproject.toml is invalid TOML: {key}"
    ),
    # Workspace validation messages
    ModuleIssueCode.MISSING_WORKSPACE_SOURCE: (
        "Module '{key}' is not declared in root pyproject.toml [tool.uv.sources]. Add: {key} = {{ workspace = true }}"
    ),
    ModuleIssueCode.MISSING_WORKSPACE_MEMBER: (
        "Module folder not matched by [tool.uv.workspace].members globs. Module at '{key}' may not be discovered by uv."
    ),
}


@dataclass
class ModuleIssue:
    code: ModuleIssueCode
    message: str
    module_path: Path


def create_issue(code: ModuleIssueCode, *, module_path: Path, key: Optional[str] = None) -> ModuleIssue:
    template = ISSUE_MESSAGES.get(
        code,
        "Module reported issue '{code}' for path '{path}'.",
    )
    message = template.format(key=key, code=code, path=str(module_path))
    return ModuleIssue(code=code, message=message, module_path=module_path)

def create_issues(info: Dict[str, Any], module_path: Path) -> List[ModuleIssue]:
    issues: List[ModuleIssue] = []
    for key, value in info.items():
        code = REQUIRED_INIT_KEYS.get(key)
        if code is None:
            continue
        if isinstance(value, str):
            present = bool(value.strip())
        elif value is None:
            present = False
        else:
            present = True
        if not present:
            issue = create_issue(code, module_path=module_path, key=key)
            issues.append(issue)
    return issues
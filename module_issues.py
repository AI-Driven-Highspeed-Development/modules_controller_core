from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional
from pathlib import Path


class ModuleIssueCode(str, Enum):
    MISSING_INIT_YAML = "missing_init_yaml"
    MISSING_VERSION = "missing_version"
    MISSING_TYPE = "missing_type"
    MISSING_REQUIREMENTS = "missing_requirements"
    MISSING_REPO_URL = "missing_repo_url"



# Map keys to issue codes for simple presence validation
REQUIRED_INIT_KEYS: Dict[str, ModuleIssueCode] = {
    "version": ModuleIssueCode.MISSING_VERSION,
    "type": ModuleIssueCode.MISSING_TYPE,
    "requirements": ModuleIssueCode.MISSING_REQUIREMENTS,
    "repo_url": ModuleIssueCode.MISSING_REPO_URL,
}

# Message templates per issue code (use {key} placeholder)
ISSUE_MESSAGES: Dict[ModuleIssueCode, str] = {
    ModuleIssueCode.MISSING_INIT_YAML: (
        "Module is missing init.yaml. Please add an init.yaml file with the required metadata keys."
    ),
    ModuleIssueCode.MISSING_VERSION: (
        "Module is missing '{key}' in init.yaml. Specify a semantic version such as '0.0.1' under the '{key}' key."
    ),
    ModuleIssueCode.MISSING_TYPE: (
        "Module is missing '{key}' in init.yaml. Set the module's type (core, manager, plugin, util, mcp) under the '{key}' key."
    ),
    ModuleIssueCode.MISSING_REQUIREMENTS: (
        "Module is missing '{key}' in init.yaml. Include a list (can be empty) of required ADHD modules under the '{key}' key."
    ),
    ModuleIssueCode.MISSING_REPO_URL: (
        "Module is missing '{key}' in init.yaml. Please add a canonical repository URL under the '{key}' key."
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
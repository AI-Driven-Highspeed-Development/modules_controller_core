# Modules Controller Core

Central registry that scans every module folder, validates metadata, and surfaces actionable reports for tooling.

## Overview
- Discovers module directories under `cores/`, `managers/`, `plugins/`, `utils/`, and `mcps/`
- Loads module metadata from `pyproject.toml` (with legacy `init.yaml` fallback)
- Derives module category from folder location and reads `layer` from `[tool.adhd]`
- Provides cached `ModulesReport` objects for fast reuse by CLIs and other automation

## Features
- **Single scan, cached results** – `list_all_modules()` exposes the previous scan unless `scan_all_modules()` is called again
- **Issue catalog** – `ModuleIssueCode` enumerates missing metadata (version, layer, requirements, repo_url)
- **Rich module info** – `ModuleInfo` stores name, version, layer, folder, repo URL, path, requirements, and attached issues
- **Helpers for pyproject.toml** – update specific keys or read metadata from `[tool.adhd]` section
- **Folder detection** – derives module folder (cores/managers/utils/plugins/mcps) from filesystem path
- **Refresh Script Support** – Detects and executes `refresh.py` scripts via `run_module_refresh_script`.
- **Module Lookup** – Find modules by name using `get_module_by_name`.

## Quickstart

```python
from pathlib import Path
from cores.modules_controller_core.modules_controller import ModulesController

project_root = Path.cwd()  # or any project directory you want to inspect
controller = ModulesController(root_path=project_root)
report = controller.list_all_modules()

print(f"Total modules: {len(report.modules)}")
for module in report.issued_modules:
	issue_codes = ", ".join(issue.code.value for issue in module.issues)
	print(f"{module.name} ({module.folder}/{module.layer}) -> {issue_codes}")

# Find a specific module
logger_module = controller.get_module_by_name("logger_util")
if logger_module:
    # Run its refresh script
    controller.run_module_refresh_script(logger_module)
```

## API

```python
@dataclass
class ModuleInfo:
	name: str
	version: str
	folder: str          # cores | managers | utils | plugins | mcps
	layer: str           # foundation | runtime | dev
	path: pathlib.Path
	repo_url: str | None = None
	is_mcp: bool = False  # True if mcp = true in [tool.adhd]
	requirements: list[str] = field(default_factory=list)
	issues: list[ModuleIssue] = field(default_factory=list)
	shows_in_workspace: bool | None = None
	def has_refresh_script(self) -> bool: ...
	def has_initializer(self) -> bool: ...

@dataclass
class ModulesReport:
	modules: list[ModuleInfo]
	issued_modules: list[ModuleInfo]

class ModulesController:
	def list_all_modules(self) -> ModulesReport: ...
	def scan_all_modules(self) -> ModulesReport: ...
	def get_module_by_name(self, module_name: str) -> Optional[ModuleInfo]: ...
	def run_module_refresh_script(self, module: ModuleInfo, ...) -> None: ...

@dataclass
class ModuleIssue:
	code: ModuleIssueCode
	message: str
	module_path: pathlib.Path

class ModuleIssueCode(str, Enum): ...  # see module_issues.py for the full list
```

## Notes
- `ModulesController` is a singleton; repeated instantiations reuse the cached report unless `scan_all_modules()` is invoked.
- `ModuleInfo.folder` is derived from the parent directory (e.g., `cores/`, `managers/`).
- `ModuleInfo.layer` comes from `[tool.adhd].layer` in pyproject.toml.
- Issue detection treats blank strings as missing values to align with metadata requirements.

## Requirements & prerequisites
- No additional pip dependencies (relies on Python standard library plus other ADHD Framework cores)

## Troubleshooting
- **Module missing from report** – ensure its directory is directly under one of the known folders and not prefixed with `_` or `.`.
- **Every module reports `missing_repo_url`** – run Module Creator Core or manually add `repo_url` to `[tool.adhd]` in pyproject.toml.
- **Missing layer warning** – ensure `[tool.adhd].layer` is set to `foundation`, `runtime`, or `dev` in pyproject.toml.

## Module structure

```
cores/modules_controller_core/
├─ __init__.py              # package marker
├─ modules_controller.py    # scanner + cache + report helpers
├─ module_filter.py         # filtering by folder, layer, etc.
├─ module_issues.py         # issue codes and helpers
├─ pyproject.toml           # module metadata
└─ README.md                # this file
```

## See also
- Config Manager – provides the configuration root paths
- YAML Reading Core – used to parse module metadata
- Module Creator Core – ensures new modules ship with compliant init files
- GitHub API Core – often used alongside module metadata for repository automation
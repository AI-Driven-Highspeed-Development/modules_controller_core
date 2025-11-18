# Modules Controller Core

Central registry that scans every module folder, validates metadata, and surfaces actionable reports for tooling.

## Overview
- Discovers module directories under `cores/`, `managers/`, `plugins/`, `utils/`, and `mcps/`
- Loads each module’s `init.yaml` using YAML Reading Core and records key metadata
- Classifies modules via strongly typed `ModuleType` objects and enumerates issues per module
- Provides cached `ModulesReport` objects for fast reuse by CLIs and other automation

## Features
- **Single scan, cached results** – `list_all_modules()` exposes the previous scan unless `scan_all_modules()` is called again
- **Issue catalog** – `ModuleIssueCode` enumerates missing metadata (version, type, requirements, repo_url, init.yaml)
- **Rich module info** – `ModuleInfo` stores name, version, module type, repo URL, path, requirements, and attached issues
- **Helpers for init.yaml** – update specific keys or overwrite entire metadata files via `update_module_init_yaml*`
- **Module type registry** – `ModuleTypes` exposes per-type paths, names, and plural forms for other tooling

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
	print(f"{module.name} ({module.module_type.name}) -> {issue_codes}")

# Update a field in init.yaml when needed
controller.update_module_init_yaml_field(module.path, "repo_url", "https://github.com/org/module.git")
```

## API

```python
@dataclass
class ModuleInfo:
	name: str
	version: str
	module_type: ModuleType
	path: pathlib.Path
	repo_url: str | None = None
	requirements: list[str] = field(default_factory=list)
	issues: list[ModuleIssue] = field(default_factory=list)

@dataclass
class ModulesReport:
	modules: list[ModuleInfo]
	issued_modules: list[ModuleInfo]

class ModulesController:
	def list_all_modules(self) -> ModulesReport: ...
	def scan_all_modules(self) -> ModulesReport: ...
	def get_module_init_yaml(self, module_path: pathlib.Path) -> dict[str, Any]: ...
	def update_module_init_yaml(self, module_path: pathlib.Path, data: dict[str, Any]) -> None: ...
	def update_module_init_yaml_field(self, module_path: pathlib.Path, key: str, value: Any) -> None: ...

class ModuleTypes:
	def get_all_types(self) -> list[ModuleType]: ...
	def get_module_type(self, name: ModuleTypeEnum | str) -> ModuleType: ...

@dataclass
class ModuleIssue:
	code: ModuleIssueCode
	message: str
	module_path: pathlib.Path

class ModuleIssueCode(str, Enum): ...  # see module_issues.py for the full list
```

## Notes
- `ModulesController` is a singleton; repeated instantiations reuse the cached report unless `scan_all_modules()` is invoked.
- `ModuleInfo.module_type` stores the `ModuleType` instance, so use `.name` or `.enum` when logging.
- Issue detection treats blank strings as missing values to align with metadata requirements.

## Requirements & prerequisites
- No additional pip dependencies (relies on Python standard library plus other ADHD Framework cores)

## Troubleshooting
- **Module missing from report** – ensure its directory is directly under one of the known type roots and not prefixed with `_` or `.`.
- **Every module reports `missing_repo_url`** – run Module Creator Core or manually add `repo_url` to `init.yaml`.
- **Unknown module type warnings** – check `init.yaml.type` matches one of the configured types or leave it blank to use the folder’s inferred type.

## Module structure

```
cores/modules_controller_core/
├─ __init__.py              # package marker
├─ modules_controller.py    # scanner + cache + report helpers
├─ module_types.py          # ModuleTypeEnum + registry
├─ module_issues.py         # issue codes and helpers
├─ init.yaml                # module metadata
└─ README.md                # this file
```

## See also
- Config Manager – provides the configuration root paths
- YAML Reading Core – used to parse module metadata
- Module Creator Core – ensures new modules ship with compliant init files
- GitHub API Core – often used alongside module metadata for repository automation
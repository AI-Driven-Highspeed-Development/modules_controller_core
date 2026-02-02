from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple
from dataclasses import dataclass, field
from logger_util import Logger
from yaml_reading_core import YamlReadingCore as YamlReader
from .module_types import ModuleType, ModuleTypes, ModuleLayer, ModuleTypeEnum
from .module_issues import (
    ModuleIssue,
    ModuleIssueCode,
    create_issue,
    create_issues,
)
from exceptions_core import ADHDError

if TYPE_CHECKING:
    from .module_filter import ModuleFilter


class DoctorIssueSeverity(str, Enum):
    """Severity levels for doctor check issues."""
    ERROR = "error"      # Must be fixed
    WARNING = "warning"  # Should be fixed but not blocking
    INFO = "info"        # Informational only


@dataclass
class DoctorIssue:
    """Represents an issue found by the doctor command."""
    severity: DoctorIssueSeverity
    code: ModuleIssueCode
    message: str
    path: Path
    suggestion: Optional[str] = None


@dataclass
class DoctorReport:
    """Report from the doctor command."""
    issues: List[DoctorIssue] = field(default_factory=list)
    modules_checked: int = 0
    
    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == DoctorIssueSeverity.ERROR)
    
    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == DoctorIssueSeverity.WARNING)
    
    @property
    def info_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == DoctorIssueSeverity.INFO)
    
    @property
    def is_healthy(self) -> bool:
        return self.error_count == 0


@dataclass
class MigrateResult:
    """Result of a module migration."""
    module_name: str
    module_path: Path
    success: bool
    message: str
    pyproject_created: bool = False
    init_yaml_removed: bool = False


class WorkspaceGenerationMode(str, Enum):
    DEFAULT = "default"
    INCLUDE_ALL = "include_all"
    IGNORE_OVERRIDES = "ignore_overrides"

@dataclass
class ModuleInfo:
    name: str
    version: str
    module_type: ModuleType
    path: Path
    repo_url: Optional[str] = None
    requirements: List[str] = field(default_factory=list)
    issues: List[ModuleIssue] = field(default_factory=list)
    shows_in_workspace: Optional[bool] = None
    layer: Optional[ModuleLayer] = None

    def initializer_path(self) -> Path:
        return self.path / "__init__.py"

    def has_initializer(self) -> bool:
        return self.initializer_path().exists()

    def refresh_script_path(self) -> Path:
        return self.path / "refresh.py"

    def has_refresh_script(self) -> bool:
        return self.refresh_script_path().exists()
    
    def get_instructions_path(self) -> Path:
        return self.module_type.path / f"{self.name}.instructions.md"
    
    def has_instructions(self) -> bool:
        return self.get_instructions_path().exists()


@dataclass
class ModulesReport:
    modules: List[ModuleInfo] = field(default_factory=list)
    issued_modules: List[ModuleInfo] = field(default_factory=list)
    root_path: Path = Path.cwd()

    def print_report(self) -> None:
        logger = Logger(name=__class__.__name__)
        total_modules = len(self.modules)
        total_issues = sum(len(module.issues) for module in self.modules)

        logger.info(f"Total modules: {total_modules}")
        logger.info(f"Total issues: {total_issues}")

        if total_issues == 0:
            logger.info("No module issues detected.")
            return

        logger.info("Modules with issues:")
        for module in self.issued_modules:
            try:
                display_path = module.path.relative_to(self.root_path)
            except ValueError:
                display_path = module.path
            logger.info(f"- {module.name} ({module.module_type.name}) -> {display_path}")
            for issue in module.issues:
                logger.info(f"  [{issue.code}] {issue.message}")


class ModulesController:
    _instances: dict[Path, "ModulesController"] = {}
    
    def __new__(cls, root_path: Optional[Path] = None) -> "ModulesController":
        root = (root_path or Path.cwd()).resolve()
        instance = cls._instances.get(root)
        if instance is None:
            instance = super().__new__(cls)
            instance._initialized = False
            cls._instances[root] = instance
        return instance
    
    def __init__(self, root_path: Optional[Path] = None):
        root = (root_path or Path.cwd()).resolve()
        if getattr(self, "_initialized", False) and getattr(self, "root_path", None) == root:
            return
        self.root_path = root
        self.logger = Logger(name=__class__.__name__)
        self.module_types = ModuleTypes(root_path=root)
        self._report: Optional[ModulesReport] = None
        self._initialized = True
    
    def list_all_modules(self) -> ModulesReport:
        """Return cached scan results, scanning once if needed."""
        if self._report is None:
            return self.scan_all_modules()
        return self._report

    def scan_all_modules(self) -> ModulesReport:
        """Scan module type folders and return a report for each discovered module.

        A module is any immediate subdirectory of one of the known type roots
        (cores/, managers/, plugins/, utils/, mcps/) that contains a pyproject.toml
        with [tool.adhd] configuration.
        """
        modules: List[ModuleInfo] = []
        issued_modules: List[ModuleInfo] = []
        for mt in self.module_types.get_all_types():
            base_dir = (mt.path if isinstance(mt.path, Path) else Path(str(mt.path))).resolve()
            if not base_dir.exists() or not base_dir.is_dir():
                continue
            for child in base_dir.iterdir():
                if not child.is_dir() or child.name.startswith(".") or child.name.startswith("__"):
                    continue
                
                pyproject_file = child / "pyproject.toml"
                if not pyproject_file.exists():
                    # Skip directories without pyproject.toml (not a module)
                    continue
                
                try:
                    pyproject_data = self.get_module_pyproject(child)
                except (FileNotFoundError, ValueError) as e:
                    mi = ModuleInfo(
                        name=child.name,
                        version="unknown",
                        module_type=mt,
                        path=child,
                        requirements=[]
                    )
                    issue = create_issue(
                        ModuleIssueCode.MISSING_INIT_YAML,  # Reuse for "missing config"
                        module_path=pyproject_file,
                    )
                    mi.issues.append(issue)
                    try:
                        display_path = pyproject_file.relative_to(self.root_path)
                    except ValueError:
                        display_path = pyproject_file
                    self.logger.warning(
                        f"[{issue.code}] {mi.name}: Invalid pyproject.toml (file: {display_path})"
                    )
                    modules.append(mi)
                    issued_modules.append(mi)
                    continue

                name = child.name
                project_data = pyproject_data.get("project", {})
                adhd_data = pyproject_data.get("tool", {}).get("adhd", {})
                urls_data = project_data.get("urls", {})

                info: Dict[str, Any] = {
                    "version": project_data.get("version"),
                    "type": adhd_data.get("type"),
                    "repo_url": urls_data.get("Repository"),
                    "requirements": project_data.get("dependencies", []),
                    "shows_in_workspace": adhd_data.get("shows_in_workspace"),
                    "layer": adhd_data.get("layer"),
                }

                issues = create_issues(info, module_path=pyproject_file)
                requirements_value = info.get("requirements")
                if not isinstance(requirements_value, list):
                    requirements_value = []

                # Validate and parse layer
                layer_str = info.get("layer")
                layer_value: Optional[ModuleLayer] = None
                if layer_str is None:
                    # Missing layer - create issue
                    issue = create_issue(
                        ModuleIssueCode.MISSING_LAYER,
                        module_path=pyproject_file,
                        key="layer",
                    )
                    issues.append(issue)
                elif not ModuleLayer.validate(layer_str):
                    # Invalid layer value
                    issue = create_issue(
                        ModuleIssueCode.INVALID_LAYER,
                        module_path=pyproject_file,
                        key=layer_str,
                    )
                    issues.append(issue)
                else:
                    layer_value = ModuleLayer.from_string(layer_str)
                    # Validate type-layer combination (cores cannot be runtime)
                    if mt.enum == ModuleTypeEnum.CORE and layer_value == ModuleLayer.RUNTIME:
                        issue = create_issue(
                            ModuleIssueCode.INVALID_TYPE_LAYER_COMBO,
                            module_path=pyproject_file,
                            key=layer_value.value,
                        )
                        issues.append(issue)

                # Build module info and collect any issues
                mi = ModuleInfo(
                    name=name,
                    version=str(info["version"]) if info["version"] is not None else "0.0.0",
                    module_type=mt,
                    path=child,
                    repo_url=str(info["repo_url"]) if isinstance(info["repo_url"], str) and info["repo_url"].strip() else None,
                    requirements=requirements_value,
                    shows_in_workspace=info["shows_in_workspace"] if isinstance(info["shows_in_workspace"], bool) else None,
                    layer=layer_value,
                    issues=issues,
                )
                for issue in issues:
                    try:
                        display_path = issue.module_path.relative_to(self.root_path)
                    except ValueError:
                        display_path = issue.module_path
                    self.logger.warning(
                        f"[{issue.code}] {name}: {issue.message} (file: {display_path})"
                    )
                modules.append(mi)
                if issues:
                    issued_modules.append(mi)
                
        report = ModulesReport(modules=modules, issued_modules=issued_modules, root_path=self.root_path)
        self._report = report
        return report
                        
                        
    def get_module_init_yaml(self, module_path: Path) -> Dict[str, Any]:
        """Read init.yaml for a module directory and return its contents as a dict.

        Raises FileNotFoundError if the file is missing or invalid per YamlReader semantics.
        
        DEPRECATED: Use get_module_pyproject() instead. This method is retained for
        backward compatibility during the migration period.
        """
        module_path = Path(module_path)
        init_file = module_path / "init.yaml"
        yf = YamlReader.read_yaml(init_file)
        data: Dict[str, Any] = yf.to_dict() if yf else {}
        if not data:
            # Treat empty or invalid data as missing file for callers
            raise FileNotFoundError(f"Invalid or empty init.yaml at {init_file}")
        return data

    def get_module_pyproject(self, module_path: Path) -> Dict[str, Any]:
        """Read pyproject.toml for a module directory and return its contents as a dict.

        Raises FileNotFoundError if the file is missing.
        Raises ValueError if the TOML is invalid or missing [tool.adhd] section.
        """
        module_path = Path(module_path)
        pyproject_file = module_path / "pyproject.toml"
        if not pyproject_file.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {pyproject_file}")
        
        with pyproject_file.open("rb") as f:
            data = tomllib.load(f)
        
        # Validate that [tool.adhd] section exists
        if "tool" not in data or "adhd" not in data.get("tool", {}):
            raise ValueError(f"Missing [tool.adhd] section in {pyproject_file}")
        
        return data

    def update_module_init_yaml(self, module_path: Path, data: Dict[str, Any]) -> None:
        """Update or create init.yaml for a module directory with the given data."""
        module_path = Path(module_path)
        init_file = module_path / "init.yaml"
        YamlReader.write_yaml(init_file, data)

    def update_module_init_yaml_field(
        self,
        module_path: Path,
        key: str,
        value: Any,
    ) -> None:
        """Update or create a single field in init.yaml for a module directory."""
        module_path = Path(module_path)
        init_file = module_path / "init.yaml"
        data: Dict[str, Any] = {}
        try:
            yf = YamlReader.read_yaml(init_file)
            if yf:
                data = yf.to_dict()
        except FileNotFoundError:
            pass  # Will create new init.yaml

        data[key] = value
        YamlReader.write_yaml(init_file, data)

    def get_module_by_name(self, module_name: str) -> Optional[ModuleInfo]:
        """Find a module by its name (case-insensitive).
        
        Supports 'type/name' format (e.g. 'managers/config_manager') by stripping the prefix.
        """
        report = self.list_all_modules()
        
        # Handle 'type/name' format
        if "/" in module_name:
            module_name = module_name.split("/")[-1]
            
        target_name = module_name.lower().strip()
        for module in report.modules:
            if module.name.lower() == target_name:
                return module
        return None

    def run_module_initializer(
        self,
        module: ModuleInfo,
        *,
        project_root: Optional[Path] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Execute the __init__.py for a single module if present."""
        if not module.has_initializer():
            return

        target_root = Path(project_root).resolve() if project_root else self.root_path
        log = logger or self.logger
        init_py = module.initializer_path()
        cmd = [sys.executable, str(init_py)]
        try:
            log.info(f"Running initializer for {module.name}")
            subprocess.run(
                cmd,
                cwd=str(target_root),
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = str(exc)
            raise ADHDError(f"Initializer failed for {module.name}: {detail}") from exc

    def _refresh_uses_relative_imports(self, refresh_path: Path) -> bool:
        """Check if a refresh.py uses relative imports from its package."""
        try:
            content = refresh_path.read_text()
            # Check for relative import patterns like: from .something or from ..something
            import re
            return bool(re.search(r'^\s*from\s+\.', content, re.MULTILINE))
        except Exception:
            return False  # Assume no relative imports if we can't read the file

    def run_module_refresh_script(
        self,
        module: ModuleInfo,
        *,
        project_root: Optional[Path] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Execute the refresh.py for a single module if present.
        
        Runs the refresh script as a module (-m) if it uses relative imports,
        otherwise runs directly as a script to avoid loading heavy __init__.py.
        """
        if not module.has_refresh_script():
            return

        target_root = Path(project_root).resolve() if project_root else self.root_path
        log = logger or self.logger
        refresh_py = module.refresh_script_path()
        
        # Check if refresh script uses relative imports
        uses_relative = self._refresh_uses_relative_imports(refresh_py)
        
        if uses_relative:
            # Run as module to preserve package context for relative imports
            # Determine the module's parent directory relative to root
            try:
                rel_path = module.path.relative_to(target_root)
                parts = rel_path.parts
                if len(parts) > 1:
                    # Module is under a subdirectory (e.g., mcps/adhd_mcp)
                    # Add the parent directory to PYTHONPATH
                    parent_dir = target_root / parts[0]
                    env = os.environ.copy()
                    existing_path = env.get("PYTHONPATH", "")
                    env["PYTHONPATH"] = f"{parent_dir}:{existing_path}" if existing_path else str(parent_dir)
                else:
                    env = None
            except ValueError:
                env = None
            
            module_name = f"{module.name}.refresh"
            cmd = [sys.executable, "-m", module_name]
        else:
            # Run directly as script - no relative imports, avoids loading __init__.py
            cmd = [sys.executable, str(refresh_py)]
            env = None
        
        try:
            log.info(f"Running refresh script for {module.name}")
            subprocess.run(
                cmd,
                cwd=str(target_root),
                check=True,
                env=env,
            )
        except subprocess.CalledProcessError as exc:
            detail = str(exc)
            raise ADHDError(f"Refresh script failed for {module.name}: {detail}") from exc

    def run_initializers(
        self,
        modules: Optional[Iterable[ModuleInfo]] = None,
        *,
        project_root: Optional[Path] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Execute initializers for the provided modules or for all known modules."""
        if modules is None:
            modules_to_run = self.list_all_modules().modules
        else:
            modules_to_run = list(modules)

        for module in modules_to_run:
            self.run_module_initializer(
                module,
                project_root=project_root,
                logger=logger,
            )

    def generate_workspace_file(
        self,
        mode: WorkspaceGenerationMode = WorkspaceGenerationMode.DEFAULT,
        overrides: Optional[Dict[str, bool]] = None,
        module_filter: Optional["ModuleFilter"] = None,
    ) -> Path:
        """Generate a VS Code workspace file listing modules based on the selected mode.
        
        This method handles module enumeration and visibility filtering, then delegates
        the actual file generation to workspace_core.generate_workspace_file().
        
        Args:
            mode: Controls visibility behavior (DEFAULT, INCLUDE_ALL, IGNORE_OVERRIDES)
            overrides: Optional dict of module_name -> visibility override
            module_filter: Optional ModuleFilter to pre-filter modules. When provided with
                filters, the filtered result is included directly (overrides default visibility).
            
        Returns:
            Path to the generated workspace file.
            
        Note:
            When an explicit filter is provided (module_filter with has_filters=True),
            the filter result is the final word - all filtered modules are included
            regardless of their shows_in_workspace setting. This allows explicit filter
            flags like `-i foundation` or `-i core` to include modules that are normally
            hidden in the default workspace view.
        """
        report = self.list_all_modules()
        modules = report.modules
        
        # Apply module filter first (if provided)
        # When an explicit filter is provided, the filter result is the final word
        # (skip visibility checks - user explicitly requested these modules)
        filter_provided = module_filter is not None and module_filter.has_filters
        if filter_provided:
            modules = module_filter.filter_modules(modules)
        
        # Build list of visible modules with their paths
        visible_modules: List[Dict[str, Any]] = []

        for module in modules:
            # If explicit filter was provided, include all filtered modules directly
            # (filter overrides default visibility)
            if filter_provided:
                is_visible = True
            elif overrides and module.name in overrides:
                is_visible = overrides[module.name]
            elif mode == WorkspaceGenerationMode.INCLUDE_ALL:
                is_visible = True
            elif mode == WorkspaceGenerationMode.IGNORE_OVERRIDES:
                is_visible = module.module_type.shows_in_workspace
            else:  # DEFAULT
                is_visible = module.shows_in_workspace
                if is_visible is None:
                    is_visible = module.module_type.shows_in_workspace

            if not is_visible:
                continue

            visible_modules.append({
                "path": module.path,
                "name": module.name,
            })

        # Lazy import to avoid layer violation at module level
        # (modules_controller_core is foundation, workspace_core is dev)
        from workspace_core import generate_workspace_file as ws_generate
        
        return ws_generate(
            modules_data=visible_modules,
            root_path=self.root_path,
        )

    # ========================================================================
    # MIGRATE COMMAND
    # ========================================================================

    def migrate_module(
        self,
        module_path: Path,
        *,
        dry_run: bool = False,
        keep_init_yaml: bool = False,
    ) -> MigrateResult:
        """Migrate a module from init.yaml to pyproject.toml format.
        
        Args:
            module_path: Path to the module directory
            dry_run: If True, only show what would be done without making changes
            keep_init_yaml: If True, don't delete init.yaml after migration
            
        Returns:
            MigrateResult with status and details
        """
        module_path = Path(module_path).resolve()
        module_name = module_path.name
        init_yaml_path = module_path / "init.yaml"
        pyproject_path = module_path / "pyproject.toml"
        
        # Check if init.yaml exists
        if not init_yaml_path.exists():
            return MigrateResult(
                module_name=module_name,
                module_path=module_path,
                success=True,
                message="No init.yaml found (already migrated or not a legacy module)",
            )
        
        # Check if pyproject.toml already exists
        if pyproject_path.exists():
            # Orphaned init.yaml - just need to remove it
            if dry_run:
                return MigrateResult(
                    module_name=module_name,
                    module_path=module_path,
                    success=True,
                    message=f"Would remove orphaned init.yaml (pyproject.toml already exists)",
                )
            
            if not keep_init_yaml:
                init_yaml_path.unlink()
                return MigrateResult(
                    module_name=module_name,
                    module_path=module_path,
                    success=True,
                    message="Removed orphaned init.yaml (pyproject.toml already exists)",
                    init_yaml_removed=True,
                )
            else:
                return MigrateResult(
                    module_name=module_name,
                    module_path=module_path,
                    success=True,
                    message="Kept orphaned init.yaml (--keep flag, pyproject.toml already exists)",
                )
        
        # Read init.yaml data
        try:
            init_data = self.get_module_init_yaml(module_path)
        except FileNotFoundError as e:
            return MigrateResult(
                module_name=module_name,
                module_path=module_path,
                success=False,
                message=f"Failed to read init.yaml: {e}",
            )
        
        # Convert to pyproject.toml format
        pyproject_content = self._convert_init_yaml_to_pyproject(module_name, init_data)
        
        if dry_run:
            return MigrateResult(
                module_name=module_name,
                module_path=module_path,
                success=True,
                message=f"Would create pyproject.toml and {'keep' if keep_init_yaml else 'remove'} init.yaml",
            )
        
        # Write pyproject.toml
        try:
            pyproject_path.write_text(pyproject_content)
        except IOError as e:
            return MigrateResult(
                module_name=module_name,
                module_path=module_path,
                success=False,
                message=f"Failed to write pyproject.toml: {e}",
            )
        
        # Remove init.yaml unless --keep
        init_removed = False
        if not keep_init_yaml:
            try:
                init_yaml_path.unlink()
                init_removed = True
            except IOError as e:
                self.logger.warning(f"Failed to remove init.yaml: {e}")
        
        return MigrateResult(
            module_name=module_name,
            module_path=module_path,
            success=True,
            message=f"Migrated to pyproject.toml" + (" (init.yaml kept)" if keep_init_yaml else ""),
            pyproject_created=True,
            init_yaml_removed=init_removed,
        )

    def _convert_init_yaml_to_pyproject(self, module_name: str, init_data: Dict[str, Any]) -> str:
        """Convert init.yaml data to pyproject.toml content string.
        
        Args:
            module_name: Name of the module (used for package name)
            init_data: Dictionary from init.yaml
            
        Returns:
            String content for pyproject.toml
        """
        version = init_data.get("version", "0.0.1")
        module_type = init_data.get("type", "core")
        repo_url = init_data.get("repo_url", "")
        shows_in_workspace = init_data.get("shows_in_workspace")
        
        # Convert module name to package name (snake_case to kebab-case)
        package_name = module_name.replace("_", "-")
        
        # Build pyproject.toml content
        lines = [
            "[project]",
            f'name = "{package_name}"',
            f'version = "{version}"',
            f'description = "ADHD Framework {module_type}: {module_name}"',
            'requires-python = ">=3.11"',
            "dependencies = []",
            "",
        ]
        
        # Add repository URL if present
        if repo_url:
            lines.extend([
                "[project.urls]",
                f'Repository = "{repo_url}"',
                "",
            ])
        
        # Add ADHD section
        lines.append("[tool.adhd]")
        lines.append(f'type = "{module_type}"')
        if shows_in_workspace is not None:
            lines.append(f'shows_in_workspace = {"true" if shows_in_workspace else "false"}')
        lines.append("")
        
        # Add build system
        lines.extend([
            "[build-system]",
            'requires = ["hatchling"]',
            'build-backend = "hatchling.build"',
            "",
            "[tool.hatch.build.targets.wheel]",
            'packages = ["."]',
            "",
            "[tool.hatch.build]",
            'dev-mode-dirs = [".."]',
            "",
        ])
        
        return "\n".join(lines)

    def migrate_all_modules(
        self,
        *,
        dry_run: bool = False,
        keep_init_yaml: bool = False,
    ) -> List[MigrateResult]:
        """Migrate all modules with init.yaml to pyproject.toml.
        
        Args:
            dry_run: If True, only show what would be done
            keep_init_yaml: If True, don't delete init.yaml files
            
        Returns:
            List of MigrateResult for each module processed
        """
        results: List[MigrateResult] = []
        
        # Find all directories with init.yaml
        for mt in self.module_types.get_all_types():
            base_dir = Path(mt.path).resolve()
            if not base_dir.exists() or not base_dir.is_dir():
                continue
            
            for child in base_dir.iterdir():
                if not child.is_dir() or child.name.startswith(".") or child.name.startswith("__"):
                    continue
                
                init_yaml = child / "init.yaml"
                if init_yaml.exists():
                    result = self.migrate_module(child, dry_run=dry_run, keep_init_yaml=keep_init_yaml)
                    results.append(result)
        
        # Also check root init.yaml (if exists)
        root_init = self.root_path / "init.yaml"
        if root_init.exists():
            # Skip root - it's not a module
            self.logger.info("Note: Root init.yaml found but not migrated (not a module)")
        
        return results

    # ========================================================================
    # DOCTOR COMMAND
    # ========================================================================

    def doctor_check(self) -> DoctorReport:
        """Run health checks on all modules and return a report.
        
        Checks performed:
        - pyproject.toml exists and is valid TOML
        - [project] section has name and version
        - [tool.adhd] section exists
        - No orphaned init.yaml files
        
        Returns:
            DoctorReport with all issues found
        """
        report = DoctorReport()
        
        for mt in self.module_types.get_all_types():
            base_dir = Path(mt.path).resolve()
            if not base_dir.exists() or not base_dir.is_dir():
                continue
            
            for child in base_dir.iterdir():
                if not child.is_dir() or child.name.startswith(".") or child.name.startswith("__"):
                    continue
                
                report.modules_checked += 1
                issues = self._check_module_health(child)
                report.issues.extend(issues)
        
        return report

    def _check_module_health(self, module_path: Path) -> List[DoctorIssue]:
        """Check health of a single module directory.
        
        Args:
            module_path: Path to the module directory
            
        Returns:
            List of issues found
        """
        issues: List[DoctorIssue] = []
        pyproject_path = module_path / "pyproject.toml"
        init_yaml_path = module_path / "init.yaml"
        
        # Check 1: pyproject.toml exists
        if not pyproject_path.exists():
            issues.append(DoctorIssue(
                severity=DoctorIssueSeverity.ERROR,
                code=ModuleIssueCode.MISSING_PYPROJECT,
                message=f"Module '{module_path.name}' is missing pyproject.toml",
                path=module_path,
                suggestion="Run 'adhd migrate' to convert init.yaml or create pyproject.toml manually",
            ))
            return issues  # Can't do more checks without pyproject.toml
        
        # Check 2: pyproject.toml is valid TOML
        try:
            with pyproject_path.open("rb") as f:
                data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            issues.append(DoctorIssue(
                severity=DoctorIssueSeverity.ERROR,
                code=ModuleIssueCode.INVALID_TOML,
                message=f"Module '{module_path.name}' has invalid TOML: {e}",
                path=pyproject_path,
                suggestion="Fix TOML syntax errors in pyproject.toml",
            ))
            return issues  # Can't do more checks with invalid TOML
        
        # Check 3: [tool.adhd] section exists
        if "tool" not in data or "adhd" not in data.get("tool", {}):
            issues.append(DoctorIssue(
                severity=DoctorIssueSeverity.ERROR,
                code=ModuleIssueCode.MISSING_ADHD_SECTION,
                message=f"Module '{module_path.name}' is missing [tool.adhd] section",
                path=pyproject_path,
                suggestion="Add [tool.adhd] section with 'type' field",
            ))
        
        # Check 4: [project] section has required fields
        project = data.get("project", {})
        if not project.get("name"):
            issues.append(DoctorIssue(
                severity=DoctorIssueSeverity.ERROR,
                code=ModuleIssueCode.MISSING_VERSION,
                message=f"Module '{module_path.name}' is missing 'name' in [project]",
                path=pyproject_path,
                suggestion="Add 'name' field to [project] section",
            ))
        if not project.get("version"):
            issues.append(DoctorIssue(
                severity=DoctorIssueSeverity.WARNING,
                code=ModuleIssueCode.MISSING_VERSION,
                message=f"Module '{module_path.name}' is missing 'version' in [project]",
                path=pyproject_path,
                suggestion="Add 'version' field to [project] section",
            ))
        
        # Check 5: Orphaned init.yaml
        if init_yaml_path.exists():
            issues.append(DoctorIssue(
                severity=DoctorIssueSeverity.WARNING,
                code=ModuleIssueCode.ORPHANED_INIT_YAML,
                message=f"Module '{module_path.name}' has orphaned init.yaml (deprecated)",
                path=init_yaml_path,
                suggestion=f"Run 'adhd migrate --module {module_path.name}' to remove",
            ))
        
        return issues
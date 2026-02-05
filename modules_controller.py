"""Modules Controller - Core module discovery and management for ADHD Framework.

This controller provides:
- Module discovery in modules/{foundation,runtime,dev}/ structure
- Module metadata reading from pyproject.toml
- Workspace file generation
- Module initialization and refresh script execution
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional

from logger_util import Logger
from exceptions_core import ADHDError

from .module_types import (
    ModuleLayer,
    MODULES_DIR,
    LAYER_SUBFOLDERS,
    layer_from_path,
)
from .module_issues import (
    ModuleIssue,
    ModuleIssueCode,
    create_issue,
)

if TYPE_CHECKING:
    from .module_filter import ModuleFilter


class WorkspaceGenerationMode(str, Enum):
    DEFAULT = "default"
    INCLUDE_ALL = "include_all"
    IGNORE_OVERRIDES = "ignore_overrides"


@dataclass
class ModuleInfo:
    """Information about a discovered module.
    
    Attributes:
        name: Module name (e.g., 'config_manager')
        version: Semantic version string
        layer: Module layer (foundation, runtime, dev)
        path: Absolute path to module directory
        is_mcp: Whether this is an MCP module (mcp=true in pyproject.toml)
        repo_url: Optional GitHub repository URL
        requirements: List of dependencies from pyproject.toml
        issues: List of validation issues
        shows_in_workspace: Override for workspace visibility (None = visible)
    """
    name: str
    version: str
    layer: ModuleLayer
    path: Path
    is_mcp: bool = False
    repo_url: Optional[str] = None
    requirements: List[str] = field(default_factory=list)
    issues: List[ModuleIssue] = field(default_factory=list)
    shows_in_workspace: Optional[bool] = None
    
    # Legacy compatibility - folder derived from layer
    @property
    def folder(self) -> str:
        """Return layer as folder for backward compatibility."""
        return self.layer.value if self.layer else "unknown"

    def initializer_path(self) -> Path:
        return self.path / "__init__.py"

    def has_initializer(self) -> bool:
        return self.initializer_path().exists()

    def refresh_script_path(self) -> Path:
        return self.path / "refresh.py"

    def has_refresh_script(self) -> bool:
        return self.refresh_script_path().exists()
    
    def get_instructions_path(self) -> Path:
        return self.path / f"{self.name}.instructions.md"
    
    def has_instructions(self) -> bool:
        return self.get_instructions_path().exists()
    
    def default_shows_in_workspace(self) -> bool:
        """Return default workspace visibility. All modules visible by default."""
        return True


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
            logger.info(f"- {module.name} ({module.layer.value}) -> {display_path}")
            for issue in module.issues:
                logger.info(f"  [{issue.code}] {issue.message}")


class ModulesController:
    """Controller for discovering and managing ADHD Framework modules.
    
    Discovers modules in modules/{foundation,runtime,dev}/ directories.
    """
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
        self._report: Optional[ModulesReport] = None
        self._initialized = True
    
    def list_all_modules(self) -> ModulesReport:
        """Return cached scan results, scanning once if needed."""
        if self._report is None:
            return self.scan_all_modules()
        return self._report

    def scan_all_modules(self) -> ModulesReport:
        """Scan modules/ directory and return a report for each discovered module.

        Scans modules/foundation/, modules/runtime/, modules/dev/.
        A module is any immediate subdirectory that contains a pyproject.toml
        with [tool.adhd] configuration.
        """
        modules: List[ModuleInfo] = []
        issued_modules: List[ModuleInfo] = []
        
        modules_dir = self.root_path / MODULES_DIR
        if not modules_dir.exists() or not modules_dir.is_dir():
            self.logger.warning(f"Modules directory not found: {modules_dir}")
            report = ModulesReport(modules=[], issued_modules=[], root_path=self.root_path)
            self._report = report
            return report
        
        for layer_name in LAYER_SUBFOLDERS:
            layer_dir = modules_dir / layer_name
            if not layer_dir.exists() or not layer_dir.is_dir():
                continue
            
            layer = ModuleLayer.from_string(layer_name)
            if layer is None:
                continue
                
            self._scan_layer_for_modules(layer_dir, layer, modules, issued_modules)
                
        report = ModulesReport(modules=modules, issued_modules=issued_modules, root_path=self.root_path)
        self._report = report
        return report
    
    def _scan_layer_for_modules(
        self,
        layer_dir: Path,
        layer: ModuleLayer,
        modules: List[ModuleInfo],
        issued_modules: List[ModuleInfo],
    ) -> None:
        """Scan a single layer directory for modules."""
        for child in layer_dir.iterdir():
            if not child.is_dir() or child.name.startswith(".") or child.name.startswith("__"):
                continue
            
            pyproject_file = child / "pyproject.toml"
            if not pyproject_file.exists():
                continue
            
            mi = self._create_module_info_from_path(child, layer, pyproject_file)
            modules.append(mi)
            if mi.issues:
                issued_modules.append(mi)

    def _create_module_info_from_path(
        self,
        module_dir: Path,
        layer: ModuleLayer,
        pyproject_file: Path,
    ) -> ModuleInfo:
        """Create ModuleInfo from a module directory path.
        
        Handles pyproject.toml parsing errors gracefully.
        """
        try:
            pyproject_data = self.get_module_pyproject(module_dir)
        except (FileNotFoundError, ValueError):
            return self._create_error_module_info(module_dir, layer, pyproject_file)
        
        return self._build_module_info(module_dir, layer, pyproject_file, pyproject_data)

    def _create_error_module_info(
        self,
        module_dir: Path,
        layer: ModuleLayer,
        pyproject_file: Path,
    ) -> ModuleInfo:
        """Create a ModuleInfo for a module with an invalid pyproject.toml."""
        mi = ModuleInfo(
            name=module_dir.name,
            version="unknown",
            layer=layer,
            path=module_dir,
            is_mcp=False,
            requirements=[]
        )
        issue = create_issue(
            ModuleIssueCode.MISSING_INIT_YAML,
            module_path=pyproject_file,
        )
        mi.issues.append(issue)
        self.logger.warning(f"[{issue.code}] {mi.name}: Invalid pyproject.toml")
        return mi

    def _build_module_info(
        self,
        module_dir: Path,
        layer: ModuleLayer,
        pyproject_file: Path,
        pyproject_data: Dict[str, Any],
    ) -> ModuleInfo:
        """Build ModuleInfo from parsed pyproject.toml data."""
        project_data = pyproject_data.get("project", {})
        adhd_data = pyproject_data.get("tool", {}).get("adhd", {})
        urls_data = project_data.get("urls", {})

        version = project_data.get("version", "0.0.0")
        repo_url = urls_data.get("Repository")
        requirements = project_data.get("dependencies", [])
        shows_in_workspace = adhd_data.get("shows_in_workspace")
        
        is_mcp = self._parse_mcp_flag(adhd_data)
        issues = self._validate_pyproject_fields(pyproject_file, version, requirements)
        
        if not isinstance(requirements, list):
            requirements = []

        mi = ModuleInfo(
            name=module_dir.name,
            version=str(version) if version else "0.0.0",
            layer=layer,
            path=module_dir,
            is_mcp=is_mcp,
            repo_url=str(repo_url) if isinstance(repo_url, str) and repo_url.strip() else None,
            requirements=requirements,
            shows_in_workspace=shows_in_workspace if isinstance(shows_in_workspace, bool) else None,
            issues=issues,
        )
        
        for issue in issues:
            self.logger.warning(f"[{issue.code}] {module_dir.name}: {issue.message}")
        
        return mi

    def _parse_mcp_flag(self, adhd_data: Dict[str, Any]) -> bool:
        """Parse the mcp flag from [tool.adhd] section."""
        is_mcp = adhd_data.get("mcp", False)
        if not isinstance(is_mcp, bool):
            is_mcp = str(is_mcp).lower() == "true"
        return is_mcp

    def _validate_pyproject_fields(
        self,
        pyproject_file: Path,
        version: Any,
        requirements: Any,
    ) -> List[ModuleIssue]:
        """Validate required pyproject.toml fields and return issues."""
        issues: List[ModuleIssue] = []
        
        if not version:
            issues.append(create_issue(
                ModuleIssueCode.MISSING_VERSION,
                module_path=pyproject_file,
                key="version",
            ))
        
        return issues

    def get_module_pyproject(self, module_path: Path) -> Dict[str, Any]:
        """Read pyproject.toml for a module directory and return its contents.

        Raises FileNotFoundError if the file is missing.
        Raises ValueError if the TOML is invalid or missing [tool.adhd] section.
        """
        module_path = Path(module_path)
        pyproject_file = module_path / "pyproject.toml"
        if not pyproject_file.exists():
            raise FileNotFoundError(f"pyproject.toml not found at {pyproject_file}")
        
        with pyproject_file.open("rb") as f:
            data = tomllib.load(f)
        
        if "tool" not in data or "adhd" not in data.get("tool", {}):
            raise ValueError(f"Missing [tool.adhd] section in {pyproject_file}")
        
        return data

    def get_module_by_name(self, module_name: str) -> Optional[ModuleInfo]:
        """Find a module by its name (case-insensitive).
        
        Supports 'layer/name' format (e.g. 'foundation/config_manager') by stripping the prefix.
        """
        report = self.list_all_modules()
        
        # Handle 'layer/name' format
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
            subprocess.run(cmd, cwd=str(target_root), check=True)
        except subprocess.CalledProcessError as exc:
            raise ADHDError(f"Initializer failed for {module.name}: {exc}") from exc

    def _refresh_uses_relative_imports(self, refresh_path: Path) -> bool:
        """Check if a refresh.py uses relative imports from its package."""
        try:
            content = refresh_path.read_text()
            import re
            return bool(re.search(r'^\s*from\s+\.', content, re.MULTILINE))
        except Exception:
            return False

    def run_module_refresh_script(
        self,
        module: ModuleInfo,
        *,
        project_root: Optional[Path] = None,
        logger: Optional[Logger] = None,
    ) -> None:
        """Execute the refresh.py for a single module if present."""
        if not module.has_refresh_script():
            return

        target_root = Path(project_root).resolve() if project_root else self.root_path
        log = logger or self.logger
        refresh_py = module.refresh_script_path()
        
        uses_relative = self._refresh_uses_relative_imports(refresh_py)
        
        if uses_relative:
            # Run as module to preserve package context for relative imports
            try:
                rel_path = module.path.relative_to(target_root)
                parts = rel_path.parts
                if len(parts) > 1:
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
            cmd = [sys.executable, str(refresh_py)]
            env = None
        
        try:
            log.info(f"Running refresh script for {module.name}")
            subprocess.run(cmd, cwd=str(target_root), check=True, env=env)
        except subprocess.CalledProcessError as exc:
            raise ADHDError(f"Refresh script failed for {module.name}: {exc}") from exc

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
            self.run_module_initializer(module, project_root=project_root, logger=logger)

    def generate_workspace_file(
        self,
        mode: WorkspaceGenerationMode = WorkspaceGenerationMode.DEFAULT,
        overrides: Optional[Dict[str, bool]] = None,
        module_filter: Optional["ModuleFilter"] = None,
    ) -> Path:
        """Generate a VS Code workspace file listing modules.
        
        Args:
            mode: Controls visibility behavior (DEFAULT, INCLUDE_ALL, IGNORE_OVERRIDES)
            overrides: Optional dict of module_name -> visibility override
            module_filter: Optional ModuleFilter to pre-filter modules
            
        Returns:
            Path to the generated workspace file.
        """
        report = self.list_all_modules()
        modules = report.modules
        
        # Apply module filter first (if provided)
        filter_provided = module_filter is not None and module_filter.has_filters
        if filter_provided:
            modules = module_filter.filter_modules(modules)
        
        visible_modules: List[Dict[str, Any]] = []

        for module in modules:
            if filter_provided:
                is_visible = True
            elif overrides and module.name in overrides:
                is_visible = overrides[module.name]
            elif mode == WorkspaceGenerationMode.INCLUDE_ALL:
                is_visible = True
            elif mode == WorkspaceGenerationMode.IGNORE_OVERRIDES:
                is_visible = module.default_shows_in_workspace()
            else:  # DEFAULT
                is_visible = module.shows_in_workspace
                if is_visible is None:
                    is_visible = module.default_shows_in_workspace()

            if not is_visible:
                continue

            visible_modules.append({
                "path": module.path,
                "name": module.name,
            })

        # Lazy import to avoid layer violation at module level
        from workspace_core import generate_workspace_file as ws_generate
        
        return ws_generate(modules_data=visible_modules, root_path=self.root_path)

    # ========================================================================
    # DOCTOR COMMAND (delegated)
    # ========================================================================

    def doctor_check(self):
        """Run health checks on all modules and return a report.
        
        Delegates to ModuleDoctor for actual checks.
        """
        from .module_doctor import ModuleDoctor, DoctorReport
        doctor = ModuleDoctor(self.root_path, self.logger)
        return doctor.check_all()

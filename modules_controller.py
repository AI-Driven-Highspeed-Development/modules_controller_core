from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from dataclasses import dataclass, field
from managers.config_manager import ConfigManager
from utils.logger_util.logger import Logger
from cores.yaml_reading_core.yaml_reading import YamlReadingCore as YamlReader
from cores.modules_controller_core.module_types import ModuleType, ModuleTypes
from cores.modules_controller_core.module_issues import (
    ModuleIssue,
    ModuleIssueCode,
    create_issue,
    create_issues,
)
from cores.exceptions_core.adhd_exceptions import ADHDError

@dataclass
class ModuleInfo:
    name: str
    version: str
    module_type: ModuleType
    path: Path
    repo_url: Optional[str] = None
    requirements: List[str] = field(default_factory=list)
    issues: List[ModuleIssue] = field(default_factory=list)

    def initializer_path(self) -> Path:
        """Return the expected __init__.py path for this module."""
        return self.path / "__init__.py"

    def has_initializer(self) -> bool:
        """Return True if __init__.py exists for this module."""
        return self.initializer_path().exists()


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
        self.cm = ConfigManager()
        self.config = self.cm.config.modules_controller_core
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
        (cores/, managers/, plugins/, utils/, mcps/) that contains an init.yaml.
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
                try:
                    init_data = self.get_module_init_yaml(child)
                except FileNotFoundError:
                    init_file = child / "init.yaml"
                    mi = ModuleInfo(
                        name=child.name,
                        version="unknown",
                        module_type=mt,
                        path=child,
                        requirements=[]
                    )
                    issue = create_issue(
                        ModuleIssueCode.MISSING_INIT_YAML,
                        module_path=init_file,
                    )
                    mi.issues.append(issue)
                    try:
                        display_path = issue.module_path.relative_to(self.root_path)
                    except ValueError:
                        display_path = issue.module_path
                    self.logger.warning(
                        f"[{issue.code}] {mi.name}: {issue.message} (file: {display_path})"
                    )
                    modules.append(mi)
                    issued_modules.append(mi)
                    continue

                name = child.name

                info: Dict[str, Any] = {
                    "version": init_data.get("version"),
                    "type": init_data.get("type"),
                    "repo_url": init_data.get("repo_url"),
                    "requirements": init_data.get("requirements"),
                }

                issues = create_issues(info, module_path=child / "init.yaml")
                requirements_value = info.get("requirements")
                if not isinstance(requirements_value, list):
                    requirements_value = []

                # Build module info and collect any issues
                mi = ModuleInfo(
                    name=name,
                    version=str(info["version"]) if info["version"] is not None else "0.0.0",
                    module_type=mt,
                    path=child,
                    repo_url=str(info["repo_url"]) if isinstance(info["repo_url"], str) and info["repo_url"].strip() else None,
                    requirements=requirements_value,
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
        """
        module_path = Path(module_path)
        init_file = module_path / "init.yaml"
        yf = YamlReader.read_yaml(init_file)
        data: Dict[str, Any] = yf.to_dict() if yf else {}
        if not data:
            # Treat empty or invalid data as missing file for callers
            raise FileNotFoundError(f"Invalid or empty init.yaml at {init_file}")
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
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr or exc.stdout or str(exc)
            raise ADHDError(f"Initializer failed for {module.name}: {detail}") from exc

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
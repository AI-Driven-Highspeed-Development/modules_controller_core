from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
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

root = Path.cwd()

@dataclass
class ModuleInfo:
    name: str
    version: str
    module_type: ModuleType
    path: Path
    repo_url: Optional[str] = None
    requirements: List[str] = field(default_factory=list)
    issues: List[ModuleIssue] = field(default_factory=list)


@dataclass
class ModulesReport:
    modules: List[ModuleInfo] = field(default_factory=list)
    issued_modules: List[ModuleInfo] = field(default_factory=list)

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
                display_path = module.path.relative_to(root)
            except ValueError:
                display_path = module.path
            logger.info(f"- {module.name} ({module.module_type.name}) -> {display_path}")
            for issue in module.issues:
                logger.info(f"  [{issue.code}] {issue.message}")


class ModulesController:
    _instance: "ModulesController" | None = None
    
    def __new__(cls) -> "ModulesController":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        self.logger = Logger(name=__class__.__name__)
        self.cm = ConfigManager()
        self.config = self.cm.config.modules_controller_core
        self.module_types = ModuleTypes()
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
                    self.logger.warning(
                        f"[{issue.code}] {mi.name}: {issue.message} (file: {issue.module_path.relative_to(root)})"
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
                    self.logger.warning(
                        f"[{issue.code}] {name}: {issue.message} (file: {issue.module_path.relative_to(root)})"
                    )
                modules.append(mi)
                if issues:
                    issued_modules.append(mi)
                
        report = ModulesReport(modules=modules, issued_modules=issued_modules)
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
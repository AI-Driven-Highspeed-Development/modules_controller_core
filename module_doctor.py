"""Module Doctor - Health checks for ADHD Framework modules.

Validates module structure, pyproject.toml configuration, and workspace membership.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

from .module_issues import ModuleIssueCode
from .module_types import MODULES_DIR, LAYER_SUBFOLDERS

if TYPE_CHECKING:
    from logger_util import Logger


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
    suggestion: str | None = None


@dataclass
class DoctorReport:
    """Report from the doctor command."""
    issues: List[DoctorIssue] = field(default_factory=list)
    modules_checked: int = 0
    workspace_members_declared: int = 0
    
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


class ModuleDoctor:
    """Health checker for ADHD Framework modules."""
    
    def __init__(self, root_path: Path, logger: "Logger"):
        self.root_path = root_path
        self.logger = logger
    
    def check_all(self) -> DoctorReport:
        """Run health checks on all modules and return a report.
        
        Checks performed:
        - pyproject.toml exists and is valid TOML
        - [project] section has name and version
        - [tool.adhd] section exists
        - No orphaned init.yaml files
        - Workspace validation: modules declared in root pyproject.toml
        
        Returns:
            DoctorReport with all issues found
        """
        report = DoctorReport()
        
        # Get workspace info from root pyproject.toml
        workspace_sources = self._get_workspace_sources()
        report.workspace_members_declared = len(workspace_sources)
        
        # Collect all discovered modules for workspace validation
        discovered_modules: List[Tuple[Path, str]] = []
        
        # Scan modules/ structure only
        modules_dir = self.root_path / MODULES_DIR
        if modules_dir.exists() and modules_dir.is_dir():
            for layer_name in LAYER_SUBFOLDERS:
                layer_dir = modules_dir / layer_name
                if not layer_dir.exists() or not layer_dir.is_dir():
                    continue
                
                for child in layer_dir.iterdir():
                    if not child.is_dir() or child.name.startswith(".") or child.name.startswith("__"):
                        continue
                    
                    report.modules_checked += 1
                    issues = self._check_module_health(child)
                    report.issues.extend(issues)
                    
                    # Track module for workspace validation
                    package_name = child.name.replace("_", "-")
                    discovered_modules.append((child, package_name))
        
        # Workspace validation
        workspace_issues = self._validate_workspace_members(discovered_modules, workspace_sources)
        report.issues.extend(workspace_issues)
        
        return report

    def _get_workspace_sources(self) -> set[str]:
        """Get the set of package names declared in root pyproject.toml [tool.uv.sources]."""
        root_pyproject = self.root_path / "pyproject.toml"
        if not root_pyproject.exists():
            return set()
        
        try:
            with root_pyproject.open("rb") as f:
                data = tomllib.load(f)
            
            sources = data.get("tool", {}).get("uv", {}).get("sources", {})
            return set(sources.keys())
        except (tomllib.TOMLDecodeError, KeyError):
            return set()

    def _validate_workspace_members(
        self,
        discovered_modules: List[Tuple[Path, str]],
        workspace_sources: set[str],
    ) -> List[DoctorIssue]:
        """Validate that all discovered modules are declared in workspace sources."""
        issues: List[DoctorIssue] = []
        
        for module_path, package_name in discovered_modules:
            if package_name not in workspace_sources:
                issues.append(DoctorIssue(
                    severity=DoctorIssueSeverity.WARNING,
                    code=ModuleIssueCode.MISSING_WORKSPACE_SOURCE,
                    message=f"Module '{package_name}' is not declared in root pyproject.toml [tool.uv.sources]",
                    path=module_path,
                    suggestion=f"Add to root pyproject.toml: {package_name} = {{ workspace = true }}",
                ))
        
        return issues

    def _check_module_health(self, module_path: Path) -> List[DoctorIssue]:
        """Check health of a single module directory."""
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
                suggestion="Create pyproject.toml with [project] and [tool.adhd] sections",
            ))
            return issues
        
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
            return issues
        
        # Check 3: [tool.adhd] section exists
        if "tool" not in data or "adhd" not in data.get("tool", {}):
            issues.append(DoctorIssue(
                severity=DoctorIssueSeverity.ERROR,
                code=ModuleIssueCode.MISSING_ADHD_SECTION,
                message=f"Module '{module_path.name}' is missing [tool.adhd] section",
                path=pyproject_path,
                suggestion="Add [tool.adhd] section",
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
                suggestion="Delete the init.yaml file",
            ))
        
        return issues

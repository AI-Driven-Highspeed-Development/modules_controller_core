"""modules_controller_core - Core module for managing ADHD Framework modules.

Provides ModulesController for discovering, listing, and managing modules.
"""

from .modules_controller import (
    ModulesController,
    ModuleInfo,
    WorkspaceGenerationMode,
    DoctorIssueSeverity,
    DoctorIssue,
    DoctorReport,
    MigrateResult,
)
from .module_types import (
    ModuleLayer,
    MODULE_FOLDERS,
    HIDDEN_WORKSPACE_FOLDERS,
    folder_from_path,
    folder_shows_in_workspace,
)
from .module_issues import ModuleIssue, ModuleIssueCode
from .dependency_walker import (
    DependencyWalker,
    DependencyClosure,
    DependencyNode,
    DependencyViolation,
    ViolationType,
    format_dependency_tree,
)
from .module_filter import (
    ModuleFilter,
    FilterMode,
    FilterDimension,
    FilterInfo,
    GitState,
)

__all__ = [
    "ModulesController",
    "ModuleInfo",
    "WorkspaceGenerationMode",
    "ModuleLayer",
    "MODULE_FOLDERS",
    "HIDDEN_WORKSPACE_FOLDERS",
    "folder_from_path",
    "folder_shows_in_workspace",
    "ModuleIssue",
    "ModuleIssueCode",
    "DoctorIssueSeverity",
    "DoctorIssue",
    "DoctorReport",
    # Dependency Walker
    "DependencyWalker",
    "DependencyClosure",
    "DependencyNode",
    "DependencyViolation",
    "ViolationType",
    "format_dependency_tree",
    # Module Filter
    "ModuleFilter",
    "FilterMode",
    "FilterDimension",
    "FilterInfo",
    "GitState",
    "MigrateResult",
]

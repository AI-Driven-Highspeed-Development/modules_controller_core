"""modules_controller_core - Core module for managing ADHD Framework modules.

Provides ModulesController for discovering, listing, and managing modules.
"""

from .modules_controller import (
    ModulesController,
    ModuleInfo,
    WorkspaceGenerationMode,
)
from .module_doctor import (
    DoctorIssueSeverity,
    DoctorIssue,
    DoctorReport,
)
from .module_types import (
    ModuleLayer,
    # Layer-based constants
    MODULES_DIR,
    LAYER_SUBFOLDERS,
    LAYER_FOUNDATION,
    LAYER_RUNTIME,
    LAYER_DEV,
    # Path utilities
    folder_from_path,
    layer_from_path,
    is_in_modules_dir,
)
from .module_issues import ModuleIssue, ModuleIssueCode
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
    # Layer-based constants
    "MODULES_DIR",
    "LAYER_SUBFOLDERS",
    "LAYER_FOUNDATION",
    "LAYER_RUNTIME",
    "LAYER_DEV",
    # Path utilities
    "folder_from_path",
    "layer_from_path",
    "is_in_modules_dir",
    "ModuleIssue",
    "ModuleIssueCode",
    "DoctorIssueSeverity",
    "DoctorIssue",
    "DoctorReport",
    # Module Filter
    "ModuleFilter",
    "FilterMode",
    "FilterDimension",
    "FilterInfo",
    "GitState",
]

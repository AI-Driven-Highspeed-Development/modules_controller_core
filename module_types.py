from enum import Enum
from pathlib import Path
from typing import Optional


# Known module folders - used for path-based folder detection
MODULE_FOLDERS = ["cores", "managers", "utils", "plugins", "mcps"]

# Folders that should NOT show in workspace by default
HIDDEN_WORKSPACE_FOLDERS = {"cores"}


class ModuleLayer(str, Enum):
    """Layer classification for modules.
    
    - FOUNDATION: Bootstrap modules required for framework initialization
    - RUNTIME: Production application modules
    - DEV: Development-only tools and utilities
    """
    FOUNDATION = "foundation"
    RUNTIME = "runtime"
    DEV = "dev"
    
    @classmethod
    def from_string(cls, value: str | None) -> "ModuleLayer | None":
        """Convert string to ModuleLayer, returning None for invalid values."""
        if value is None:
            return None
        try:
            return cls(value.lower())
        except ValueError:
            return None
    
    @classmethod
    def validate(cls, value: str | None) -> bool:
        """Check if a string is a valid layer value."""
        if value is None:
            return False
        return value.lower() in [layer.value for layer in cls]
    
    @classmethod
    def get_valid_layers_for_folder(cls, folder: str) -> list["ModuleLayer"]:
        """Get valid layers for a given module folder.
        
        Cores (folder='cores') can only be FOUNDATION or DEV (never RUNTIME).
        Other folders can be any layer.
        """
        if folder == "cores":
            return [cls.FOUNDATION, cls.DEV]
        return list(cls)


def folder_from_path(module_path: Path, root_path: Optional[Path] = None) -> str:
    """Derive the folder name (cores, managers, etc.) from a module path.
    
    Args:
        module_path: Absolute or relative path to the module directory
        root_path: Optional root path for relative resolution
        
    Returns:
        Folder name (e.g., 'cores', 'managers', 'mcps')
        
    Raises:
        ValueError: If the path doesn't match a known module folder
    """
    module_path = Path(module_path).resolve()
    root = (root_path or Path.cwd()).resolve()
    
    try:
        rel_path = module_path.relative_to(root)
        parts = rel_path.parts
        if parts and parts[0] in MODULE_FOLDERS:
            return parts[0]
    except ValueError:
        pass
    
    # Fallback: check if any part of the path matches a known folder
    for part in module_path.parts:
        if part in MODULE_FOLDERS:
            return part
    
    raise ValueError(f"Cannot determine module folder from path: {module_path}")


def folder_shows_in_workspace(folder: str) -> bool:
    """Check if modules in a folder should show in workspace by default."""
    return folder not in HIDDEN_WORKSPACE_FOLDERS

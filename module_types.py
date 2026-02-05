"""Module type constants and utilities for the ADHD Framework.

This module defines the layer-based module structure:
- modules/foundation/ - Bootstrap modules required for framework initialization
- modules/runtime/    - Production application modules  
- modules/dev/        - Development-only tools and utilities
"""

from enum import Enum
from pathlib import Path
from typing import Optional, Tuple


# =============================================================================
# Layer Constants
# =============================================================================

# Layer subfolder names
LAYER_FOUNDATION = "foundation"
LAYER_RUNTIME = "runtime"
LAYER_DEV = "dev"

# The unified modules directory
MODULES_DIR = "modules"

# All layer subfolders (order matters for discovery)
LAYER_SUBFOLDERS: Tuple[str, ...] = (LAYER_FOUNDATION, LAYER_RUNTIME, LAYER_DEV)


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


def layer_from_path(module_path: Path, modules_root: Optional[Path] = None) -> Optional[str]:
    """Infer layer from physical location in the modules/ structure.
    
    Args:
        module_path: Path to the module directory
        modules_root: Path to the project root (not the modules/ directory)
        
    Returns:
        Layer name: "foundation", "runtime", or "dev"
        None if module is outside modules/ structure
    """
    module_path = Path(module_path).resolve()
    root = (modules_root or Path.cwd()).resolve()
    
    try:
        rel_path = module_path.relative_to(root)
        parts = rel_path.parts
        
        # Check if this is in the modules/ structure
        if parts and parts[0] == MODULES_DIR and len(parts) >= 2:
            layer_part = parts[1]
            if layer_part in LAYER_SUBFOLDERS:
                return layer_part
        
        return None
    except ValueError:
        # External module — cannot infer from path
        return None


def is_in_modules_dir(module_path: Path, root_path: Optional[Path] = None) -> bool:
    """Check if a module is in the modules/ structure.
    
    Args:
        module_path: Path to the module directory
        root_path: Path to the project root
        
    Returns:
        True if module is under modules/*/
    """
    module_path = Path(module_path).resolve()
    root = (root_path or Path.cwd()).resolve()
    
    try:
        rel_path = module_path.relative_to(root)
        parts = rel_path.parts
        return parts and parts[0] == MODULES_DIR and len(parts) >= 2
    except ValueError:
        return False


def folder_from_path(module_path: Path, root_path: Optional[Path] = None) -> str:
    """Derive the layer folder name from a module path.
    
    Args:
        module_path: Absolute or relative path to the module directory
        root_path: Optional root path for relative resolution
        
    Returns:
        Layer name: 'foundation', 'runtime', or 'dev'
        
    Raises:
        ValueError: If the path doesn't match modules/{layer}/ structure
    """
    module_path = Path(module_path).resolve()
    root = (root_path or Path.cwd()).resolve()
    
    try:
        rel_path = module_path.relative_to(root)
        parts = rel_path.parts
        
        # Check for modules/ structure
        if parts and parts[0] == MODULES_DIR and len(parts) >= 2:
            if parts[1] in LAYER_SUBFOLDERS:
                return parts[1]
    except ValueError:
        pass
    
    raise ValueError(f"Cannot determine module layer from path: {module_path}. Expected modules/{{foundation,runtime,dev}}/...")


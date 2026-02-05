"""Module Filter - Unified filtering system for ADHD modules.

This module provides the ModuleFilter class for filtering modules by:
- layer: foundation, runtime, dev (with inheritance)
- mcp: filter to MCP modules only (mcp = true flag)
- state: dirty, unpushed, clean (git states)

Filter modes:
- include (-i): Only modules matching the filter
- require (-r): All specified filters must match (AND logic)
- exclude (-x): Modules NOT matching the filter
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from .module_types import ModuleLayer, LAYER_SUBFOLDERS

if TYPE_CHECKING:
    from .modules_controller import ModuleInfo

# Valid folder names (layer folders only)
VALID_FOLDER_NAMES = list(LAYER_SUBFOLDERS)


class FilterMode(str, Enum):
    """Filter mode determines how filters are applied."""
    INCLUDE = "include"   # Only modules matching filter (OR logic)
    REQUIRE = "require"   # All filters must match (AND logic)
    EXCLUDE = "exclude"   # Modules NOT matching filter


class FilterDimension(str, Enum):
    """Dimensions that can be filtered."""
    LAYER = "layer"
    FOLDER = "folder"
    MCP = "mcp"
    STATE = "state"


# Git states that can be filtered
class GitState(str, Enum):
    """Git states for filtering."""
    DIRTY = "dirty"       # Has uncommitted changes
    UNPUSHED = "unpushed"  # Has commits not pushed
    CLEAN = "clean"       # No changes, up to date


# Layer inheritance: when filtering by layer, include all lower layers
# e.g., -i runtime should include runtime AND foundation
LAYER_INHERITANCE: Dict[ModuleLayer, Set[ModuleLayer]] = {
    ModuleLayer.FOUNDATION: {ModuleLayer.FOUNDATION},
    ModuleLayer.RUNTIME: {ModuleLayer.FOUNDATION, ModuleLayer.RUNTIME},
    ModuleLayer.DEV: {ModuleLayer.FOUNDATION, ModuleLayer.RUNTIME, ModuleLayer.DEV},
}


@dataclass
class FilterSpec:
    """Specification for a single filter."""
    dimension: FilterDimension
    value: str
    
    def __hash__(self):
        return hash((self.dimension, self.value))


@dataclass
class ModuleFilter:
    """Filter for selecting modules based on various criteria.
    
    Usage:
        # Include only runtime and foundation modules
        f = ModuleFilter(mode=FilterMode.INCLUDE)
        f.add_layer("runtime")  # Automatically includes foundation due to inheritance
        
        # Exclude dev modules
        f = ModuleFilter(mode=FilterMode.EXCLUDE)
        f.add_layer("dev")
        
        # Filter by folder (path-based)
        f = ModuleFilter(mode=FilterMode.INCLUDE)
        f.add_folder("managers")
        
        # Filter to MCP modules only
        f = ModuleFilter(mode=FilterMode.INCLUDE)
        f.add_mcp()
        
        # Require modules that are both in managers AND dirty
        f = ModuleFilter(mode=FilterMode.REQUIRE)
        f.add_folder("managers")
        f.add_state("dirty")
    """
    
    mode: FilterMode = FilterMode.INCLUDE
    filters: List[FilterSpec] = field(default_factory=list)
    
    # Caches for resolved filter values
    _layer_filters: Set[ModuleLayer] = field(default_factory=set, init=False, repr=False)
    _folder_filters: Set[str] = field(default_factory=set, init=False, repr=False)
    _mcp_filter: bool = field(default=False, init=False, repr=False)
    _state_filters: Set[GitState] = field(default_factory=set, init=False, repr=False)
    
    def add_layer(self, layer: str, inherit: bool = True) -> "ModuleFilter":
        """Add a layer filter.
        
        Args:
            layer: Layer name (foundation, runtime, dev)
            inherit: If True, include all lower layers (default behavior for include mode)
        """
        layer_enum = ModuleLayer.from_string(layer)
        if layer_enum is None:
            raise ValueError(f"Invalid layer: {layer}. Valid values: {[l.value for l in ModuleLayer]}")
        
        self.filters.append(FilterSpec(FilterDimension.LAYER, layer))
        
        # Apply inheritance for include mode
        if inherit and self.mode == FilterMode.INCLUDE:
            for inherited_layer in LAYER_INHERITANCE.get(layer_enum, {layer_enum}):
                self._layer_filters.add(inherited_layer)
        else:
            self._layer_filters.add(layer_enum)
        
        return self
    
    def add_folder(self, folder: str) -> "ModuleFilter":
        """Add a folder/layer filter.
        
        Accepts layer folders: foundation, runtime, dev
        """
        folder_lower = folder.lower()
        if folder_lower not in VALID_FOLDER_NAMES:
            raise ValueError(
                f"Invalid folder: {folder}. "
                f"Valid values: {VALID_FOLDER_NAMES}"
            )
        
        self.filters.append(FilterSpec(FilterDimension.FOLDER, folder))
        self._folder_filters.add(folder_lower)
        return self
    
    def add_mcp(self) -> "ModuleFilter":
        """Add MCP filter - include only modules with mcp=true flag."""
        self.filters.append(FilterSpec(FilterDimension.MCP, "true"))
        self._mcp_filter = True
        return self
    
    def add_state(self, state: str) -> "ModuleFilter":
        """Add a git state filter."""
        try:
            state_enum = GitState(state.lower())
        except ValueError:
            raise ValueError(
                f"Invalid state: {state}. "
                f"Valid values: {[s.value for s in GitState]}"
            )
        
        self.filters.append(FilterSpec(FilterDimension.STATE, state))
        self._state_filters.add(state_enum)
        return self
    
    def add_filter(self, dimension: str, value: str) -> "ModuleFilter":
        """Add a filter by dimension name.
        
        Args:
            dimension: One of 'layer', 'folder', 'mcp', 'state'
            value: The filter value
        """
        dim = FilterDimension(dimension.lower())
        if dim == FilterDimension.LAYER:
            return self.add_layer(value)
        elif dim == FilterDimension.FOLDER:
            return self.add_folder(value)
        elif dim == FilterDimension.MCP:
            return self.add_mcp()
        elif dim == FilterDimension.STATE:
            return self.add_state(value)
        else:
            raise ValueError(f"Unknown filter dimension: {dimension}")
    
    @property
    def has_filters(self) -> bool:
        """Check if any filters have been added."""
        return len(self.filters) > 0
    
    @property
    def has_state_filters(self) -> bool:
        """Check if state filters require git status lookup."""
        return len(self._state_filters) > 0
    
    def matches(
        self,
        module: "ModuleInfo",
        git_state: Optional[GitState] = None,
    ) -> bool:
        """Check if a module matches the filter criteria.
        
        Args:
            module: The module to check
            git_state: Git state of the module (required if state filters are set)
            
        Returns:
            True if module matches according to the filter mode
        """
        if not self.has_filters:
            return True  # No filters = match all
        
        matches_by_dimension: Dict[FilterDimension, bool] = {}
        
        # Check layer filter
        if self._layer_filters:
            if module.layer is None:
                matches_by_dimension[FilterDimension.LAYER] = False
            else:
                matches_by_dimension[FilterDimension.LAYER] = module.layer in self._layer_filters
        
        # Check folder filter
        if self._folder_filters:
            matches_by_dimension[FilterDimension.FOLDER] = module.folder in self._folder_filters
        
        # Check MCP filter
        if self._mcp_filter:
            matches_by_dimension[FilterDimension.MCP] = module.is_mcp
        
        # Check state filter
        if self._state_filters:
            if git_state is None:
                # State filter set but no state provided - can't match
                matches_by_dimension[FilterDimension.STATE] = False
            else:
                matches_by_dimension[FilterDimension.STATE] = git_state in self._state_filters
        
        if not matches_by_dimension:
            return True  # No filters evaluated
        
        # Apply filter mode logic
        if self.mode == FilterMode.INCLUDE:
            # OR logic: match if ANY dimension matches
            return any(matches_by_dimension.values())
        elif self.mode == FilterMode.REQUIRE:
            # AND logic: match if ALL dimensions match
            return all(matches_by_dimension.values())
        elif self.mode == FilterMode.EXCLUDE:
            # Exclusion: match if NONE of the dimensions match
            return not any(matches_by_dimension.values())
        
        return True  # Fallback
    
    def filter_modules(
        self,
        modules: List["ModuleInfo"],
        git_states: Optional[Dict[str, GitState]] = None,
    ) -> List["ModuleInfo"]:
        """Filter a list of modules.
        
        Args:
            modules: List of modules to filter
            git_states: Mapping of module names to their git states (optional)
            
        Returns:
            Filtered list of modules
        """
        if not self.has_filters:
            return modules
        
        git_states = git_states or {}
        
        return [
            m for m in modules
            if self.matches(m, git_states.get(m.name))
        ]


@dataclass
class FilterInfo:
    """Information about available filter values."""
    layers: List[str] = field(default_factory=list)
    folders: List[str] = field(default_factory=list)
    states: List[str] = field(default_factory=list)
    
    @classmethod
    def get_available(cls) -> "FilterInfo":
        """Get all available filter values."""
        return cls(
            layers=[l.value for l in ModuleLayer],
            folders=VALID_FOLDER_NAMES,  # Both legacy and new structure folders
            states=[s.value for s in GitState],
        )
    
    def format(self) -> str:
        """Format filter info for display."""
        lines = [
            "📋 Available Filters:",
            "",
            "  Layers (with inheritance for -i):",
        ]
        for layer in self.layers:
            inherited = LAYER_INHERITANCE.get(ModuleLayer(layer), set())
            inherited_str = ", ".join(l.value for l in inherited)
            lines.append(f"    • {layer} → includes: {inherited_str}")
        
        lines.extend([
            "",
            "  Folders (layer-based):",
        ])
        for f in LAYER_SUBFOLDERS:
            lines.append(f"    • {f}")
        
        lines.extend([
            "",
            "  MCP:",
            "    • --mcp: Filter to modules with mcp=true flag",
        ])
        
        lines.extend([
            "",
            "  States (git):",
        ])
        for s in self.states:
            lines.append(f"    • {s}")
        
        lines.extend([
            "",
            "  Modes:",
            "    • -i (include): Show only matching modules (OR logic)",
            "    • -r (require): Show modules matching ALL filters (AND logic)",
            "    • -x (exclude): Hide matching modules",
        ])
        
        return "\n".join(lines)

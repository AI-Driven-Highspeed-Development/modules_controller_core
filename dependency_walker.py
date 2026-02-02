"""Dependency Walker - Traverses and analyzes module dependencies.

This module provides functionality to:
1. Walk the dependency tree from a starting module
2. Build a complete closure set of all transitive dependencies
3. Detect cross-layer violations (e.g., runtime depending on dev)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

from .module_types import ModuleLayer

if TYPE_CHECKING:
    from .modules_controller import ModulesController, ModuleInfo


class ViolationType(str, Enum):
    """Types of dependency violations."""
    CROSS_LAYER = "cross_layer"  # e.g., runtime depending on dev
    MISSING_DEP = "missing_dep"  # dependency not found in project


@dataclass
class DependencyViolation:
    """Represents a dependency violation."""
    violation_type: ViolationType
    source_module: str
    source_layer: Optional[ModuleLayer]
    target_dep: str
    target_layer: Optional[ModuleLayer]
    message: str


@dataclass
class DependencyNode:
    """Represents a node in the dependency tree."""
    name: str
    layer: Optional[ModuleLayer]
    depth: int
    children: List["DependencyNode"] = field(default_factory=list)
    is_external: bool = False  # True if dependency is not an ADHD module


@dataclass
class DependencyClosure:
    """Result of walking the dependency tree."""
    root_module: str
    root_layer: Optional[ModuleLayer]
    tree: DependencyNode
    all_deps: Set[str]  # All unique dependencies (transitive closure)
    adhd_deps: Set[str]  # Only ADHD module dependencies
    external_deps: Set[str]  # External (non-ADHD) dependencies
    violations: List[DependencyViolation] = field(default_factory=list)
    
    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0


# Layer hierarchy: foundation < runtime < dev
# A module can only depend on modules at the same level or lower
LAYER_HIERARCHY: Dict[ModuleLayer, int] = {
    ModuleLayer.FOUNDATION: 0,
    ModuleLayer.RUNTIME: 1,
    ModuleLayer.DEV: 2,
}


def _can_depend_on(source_layer: Optional[ModuleLayer], target_layer: Optional[ModuleLayer]) -> bool:
    """Check if a source layer can depend on a target layer.
    
    Rules:
    - foundation can depend on: foundation
    - runtime can depend on: foundation, runtime
    - dev can depend on: foundation, runtime, dev
    
    If either layer is None, we allow the dependency (can't validate).
    """
    if source_layer is None or target_layer is None:
        return True  # Can't validate without layer info
    
    source_level = LAYER_HIERARCHY.get(source_layer, 0)
    target_level = LAYER_HIERARCHY.get(target_layer, 0)
    
    # Source can depend on target if target's level <= source's level
    return target_level <= source_level


def _package_name_to_module_name(package_name: str) -> str:
    """Convert package name (kebab-case) to module name (snake_case).
    
    Examples:
        logger-util -> logger_util
        config-manager -> config_manager
        rich>=13.0 -> rich  (external, strip version)
    """
    # Strip version specifiers
    for sep in [">=", "<=", "==", "!=", ">", "<", "~=", "[", "@"]:
        if sep in package_name:
            package_name = package_name.split(sep)[0]
    
    return package_name.strip().replace("-", "_")


class DependencyWalker:
    """Walks module dependencies and builds closure set with violation detection."""
    
    def __init__(self, controller: "ModulesController"):
        self.controller = controller
        self._module_cache: Dict[str, Optional["ModuleInfo"]] = {}
        self._visited: Set[str] = set()
    
    def _get_module(self, module_name: str) -> Optional["ModuleInfo"]:
        """Get module info by name, with caching."""
        if module_name not in self._module_cache:
            self._module_cache[module_name] = self.controller.get_module_by_name(module_name)
        return self._module_cache[module_name]
    
    def _get_module_dependencies(self, module: "ModuleInfo") -> List[str]:
        """Extract dependencies from a module's pyproject.toml.
        
        Returns list of dependency names (converted from package to module names).
        """
        try:
            pyproject = self.controller.get_module_pyproject(module.path)
            deps = pyproject.get("project", {}).get("dependencies", [])
            return [_package_name_to_module_name(d) for d in deps]
        except (FileNotFoundError, ValueError):
            return []
    
    def _is_adhd_module(self, dep_name: str) -> bool:
        """Check if a dependency name corresponds to an ADHD module."""
        return self._get_module(dep_name) is not None
    
    def walk_dependencies(
        self,
        module_name: str,
        max_depth: int = 50,
    ) -> DependencyClosure:
        """Walk the dependency tree from a starting module.
        
        Args:
            module_name: Name of the module to start from
            max_depth: Maximum recursion depth (safety limit)
            
        Returns:
            DependencyClosure with tree, closure set, and violations
        """
        self._visited.clear()
        
        root_module = self._get_module(module_name)
        if root_module is None:
            # Module not found - return empty closure with error
            return DependencyClosure(
                root_module=module_name,
                root_layer=None,
                tree=DependencyNode(name=module_name, layer=None, depth=0),
                all_deps=set(),
                adhd_deps=set(),
                external_deps=set(),
                violations=[DependencyViolation(
                    violation_type=ViolationType.MISSING_DEP,
                    source_module="<root>",
                    source_layer=None,
                    target_dep=module_name,
                    target_layer=None,
                    message=f"Root module '{module_name}' not found in project",
                )],
            )
        
        all_deps: Set[str] = set()
        adhd_deps: Set[str] = set()
        external_deps: Set[str] = set()
        violations: List[DependencyViolation] = []
        
        root_node = self._walk_recursive(
            module=root_module,
            depth=0,
            max_depth=max_depth,
            all_deps=all_deps,
            adhd_deps=adhd_deps,
            external_deps=external_deps,
            violations=violations,
        )
        
        return DependencyClosure(
            root_module=module_name,
            root_layer=root_module.layer,
            tree=root_node,
            all_deps=all_deps,
            adhd_deps=adhd_deps,
            external_deps=external_deps,
            violations=violations,
        )
    
    def _walk_recursive(
        self,
        module: "ModuleInfo",
        depth: int,
        max_depth: int,
        all_deps: Set[str],
        adhd_deps: Set[str],
        external_deps: Set[str],
        violations: List[DependencyViolation],
    ) -> DependencyNode:
        """Recursively walk dependencies."""
        node = DependencyNode(
            name=module.name,
            layer=module.layer,
            depth=depth,
        )
        
        # Prevent infinite recursion on circular dependencies
        if module.name in self._visited:
            return node
        self._visited.add(module.name)
        
        if depth >= max_depth:
            return node
        
        deps = self._get_module_dependencies(module)
        
        for dep_name in deps:
            all_deps.add(dep_name)
            
            dep_module = self._get_module(dep_name)
            
            if dep_module is None:
                # External dependency (not an ADHD module)
                external_deps.add(dep_name)
                child_node = DependencyNode(
                    name=dep_name,
                    layer=None,
                    depth=depth + 1,
                    is_external=True,
                )
                node.children.append(child_node)
            else:
                # ADHD module dependency
                adhd_deps.add(dep_name)
                
                # Check for layer violations
                if not _can_depend_on(module.layer, dep_module.layer):
                    violations.append(DependencyViolation(
                        violation_type=ViolationType.CROSS_LAYER,
                        source_module=module.name,
                        source_layer=module.layer,
                        target_dep=dep_name,
                        target_layer=dep_module.layer,
                        message=(
                            f"Layer violation: {module.name} [{module.layer.value if module.layer else '?'}] "
                            f"depends on {dep_name} [{dep_module.layer.value if dep_module.layer else '?'}]. "
                            f"A {module.layer.value if module.layer else '?'} module cannot depend on a "
                            f"{dep_module.layer.value if dep_module.layer else '?'} module."
                        ),
                    ))
                
                # Recursively walk if not already visited
                if dep_name not in self._visited:
                    child_node = self._walk_recursive(
                        module=dep_module,
                        depth=depth + 1,
                        max_depth=max_depth,
                        all_deps=all_deps,
                        adhd_deps=adhd_deps,
                        external_deps=external_deps,
                        violations=violations,
                    )
                else:
                    # Already visited, just create a leaf node
                    child_node = DependencyNode(
                        name=dep_name,
                        layer=dep_module.layer,
                        depth=depth + 1,
                    )
                node.children.append(child_node)
        
        return node


def format_dependency_tree(node: DependencyNode, prefix: str = "", is_last: bool = True) -> str:
    """Format a dependency tree for terminal output.
    
    Args:
        node: Root node of the tree
        prefix: Current line prefix for indentation
        is_last: Whether this is the last sibling
        
    Returns:
        Multi-line string representation of the tree
    """
    lines: List[str] = []
    
    # Format node label
    layer_str = f"[{node.layer.value}]" if node.layer else "[external]" if node.is_external else "[?]"
    connector = "└── " if is_last else "├── "
    
    if node.depth == 0:
        # Root node
        lines.append(f"{node.name} {layer_str}")
    else:
        lines.append(f"{prefix}{connector}{node.name} {layer_str}")
    
    # Update prefix for children
    if node.depth == 0:
        child_prefix = ""
    else:
        child_prefix = prefix + ("    " if is_last else "│   ")
    
    # Format children
    for i, child in enumerate(node.children):
        is_child_last = (i == len(node.children) - 1)
        lines.append(format_dependency_tree(child, child_prefix, is_child_last))
    
    return "\n".join(lines)

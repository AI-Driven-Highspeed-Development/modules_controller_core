"""Tests for ModuleFilter filtering by layer, folder, and mcp predicates.

This validates the unified filtering system for ADHD modules.
"""

import pytest
from pathlib import Path

from modules_controller_core import ModuleInfo
from modules_controller_core.module_filter import (
    ModuleFilter,
    FilterMode,
    FilterDimension,
    FilterSpec,
    FilterInfo,
    GitState,
    LAYER_INHERITANCE,
)
from modules_controller_core.module_types import ModuleLayer, LAYER_SUBFOLDERS


class TestFilterModes:
    """Test filter mode enum values."""

    def test_include_mode_exists(self):
        """INCLUDE mode should exist for OR-based filtering."""
        assert FilterMode.INCLUDE.value == "include"

    def test_require_mode_exists(self):
        """REQUIRE mode should exist for AND-based filtering."""
        assert FilterMode.REQUIRE.value == "require"

    def test_exclude_mode_exists(self):
        """EXCLUDE mode should exist for exclusion filtering."""
        assert FilterMode.EXCLUDE.value == "exclude"


class TestModuleFilterConstruction:
    """Test ModuleFilter initialization and configuration."""

    def test_default_filter_mode_is_include(self):
        """Default filter mode should be INCLUDE."""
        f = ModuleFilter()
        assert f.mode == FilterMode.INCLUDE

    def test_filter_mode_can_be_set(self):
        """Filter mode can be explicitly set."""
        f = ModuleFilter(mode=FilterMode.EXCLUDE)
        assert f.mode == FilterMode.EXCLUDE

    def test_empty_filter_has_no_filters(self):
        """New filter should have no filters."""
        f = ModuleFilter()
        assert not f.has_filters

    def test_filter_chaining(self):
        """Filter methods should return self for chaining."""
        f = ModuleFilter()
        result = f.add_folder("managers").add_layer("runtime")
        assert result is f
        assert f.has_filters


class TestLayerFiltering:
    """Test filtering by module layer."""

    @pytest.fixture
    def modules(self) -> list[ModuleInfo]:
        """Create test modules with different layers."""
        return [
            ModuleInfo(
                name="foundation_module",
                version="1.0.0",
                folder="cores",
                path=Path("/test"),
                layer=ModuleLayer.FOUNDATION,
            ),
            ModuleInfo(
                name="runtime_module",
                version="1.0.0",
                folder="managers",
                path=Path("/test"),
                layer=ModuleLayer.RUNTIME,
            ),
            ModuleInfo(
                name="dev_module",
                version="1.0.0",
                folder="utils",
                path=Path("/test"),
                layer=ModuleLayer.DEV,
            ),
            ModuleInfo(
                name="no_layer_module",
                version="1.0.0",
                folder="plugins",
                path=Path("/test"),
                layer=None,
            ),
        ]

    def test_layer_inheritance_foundation(self):
        """Foundation layer should only include itself."""
        inherited = LAYER_INHERITANCE[ModuleLayer.FOUNDATION]
        assert inherited == {ModuleLayer.FOUNDATION}

    def test_layer_inheritance_runtime(self):
        """Runtime layer should include foundation + runtime."""
        inherited = LAYER_INHERITANCE[ModuleLayer.RUNTIME]
        assert inherited == {ModuleLayer.FOUNDATION, ModuleLayer.RUNTIME}

    def test_layer_inheritance_dev(self):
        """Dev layer should include all layers."""
        inherited = LAYER_INHERITANCE[ModuleLayer.DEV]
        assert inherited == {ModuleLayer.FOUNDATION, ModuleLayer.RUNTIME, ModuleLayer.DEV}

    def test_add_layer_with_valid_value(self):
        """add_layer should accept valid layer values."""
        f = ModuleFilter()
        f.add_layer("runtime")
        assert f.has_filters

    def test_add_layer_with_invalid_value_raises(self):
        """add_layer should raise ValueError for invalid layers."""
        f = ModuleFilter()
        with pytest.raises(ValueError, match="Invalid layer"):
            f.add_layer("invalid_layer")

    def test_include_runtime_includes_foundation(self, modules):
        """Including runtime should also match foundation modules (inheritance)."""
        f = ModuleFilter(mode=FilterMode.INCLUDE)
        f.add_layer("runtime")
        
        filtered = f.filter_modules(modules)
        names = {m.name for m in filtered}
        
        assert "foundation_module" in names
        assert "runtime_module" in names
        assert "dev_module" not in names

    def test_exclude_dev_excludes_only_dev(self, modules):
        """Excluding dev should only exclude dev modules."""
        f = ModuleFilter(mode=FilterMode.EXCLUDE)
        f.add_layer("dev", inherit=False)
        
        filtered = f.filter_modules(modules)
        names = {m.name for m in filtered}
        
        assert "foundation_module" in names
        assert "runtime_module" in names
        assert "dev_module" not in names

    def test_module_with_no_layer_does_not_match(self, modules):
        """Module with layer=None should not match layer filters."""
        f = ModuleFilter(mode=FilterMode.INCLUDE)
        f.add_layer("foundation")
        
        filtered = f.filter_modules(modules)
        names = {m.name for m in filtered}
        
        assert "no_layer_module" not in names


class TestFolderFiltering:
    """Test filtering by module folder."""

    @pytest.fixture
    def modules(self) -> list[ModuleInfo]:
        """Create test modules in different folders."""
        return [
            ModuleInfo(name="core1", version="1.0.0", folder="cores", path=Path("/test")),
            ModuleInfo(name="manager1", version="1.0.0", folder="managers", path=Path("/test")),
            ModuleInfo(name="util1", version="1.0.0", folder="utils", path=Path("/test")),
            ModuleInfo(name="plugin1", version="1.0.0", folder="plugins", path=Path("/test")),
            ModuleInfo(name="mcp1", version="1.0.0", folder="mcps", path=Path("/test")),
        ]

    def test_add_folder_with_valid_value(self):
        """add_folder should accept valid folder values."""
        f = ModuleFilter()
        f.add_folder("managers")
        assert f.has_filters

    def test_add_folder_with_invalid_value_raises(self):
        """add_folder should raise ValueError for invalid folders."""
        f = ModuleFilter()
        with pytest.raises(ValueError, match="Invalid folder"):
            f.add_folder("nonexistent")

    def test_include_single_folder(self, modules):
        """Should filter to only modules in specified folder."""
        f = ModuleFilter(mode=FilterMode.INCLUDE)
        f.add_folder("managers")
        
        filtered = f.filter_modules(modules)
        assert len(filtered) == 1
        assert filtered[0].name == "manager1"

    def test_include_multiple_folders(self, modules):
        """Should filter to modules in any of specified folders."""
        f = ModuleFilter(mode=FilterMode.INCLUDE)
        f.add_folder("managers")
        f.add_folder("utils")
        
        filtered = f.filter_modules(modules)
        names = {m.name for m in filtered}
        
        assert names == {"manager1", "util1"}

    def test_exclude_folder(self, modules):
        """Exclude mode should remove modules in specified folder."""
        f = ModuleFilter(mode=FilterMode.EXCLUDE)
        f.add_folder("cores")
        
        filtered = f.filter_modules(modules)
        names = {m.name for m in filtered}
        
        assert "core1" not in names
        assert "manager1" in names


class TestMcpFiltering:
    """Test filtering by MCP flag."""

    @pytest.fixture
    def modules(self) -> list[ModuleInfo]:
        """Create test modules with different MCP settings."""
        return [
            ModuleInfo(
                name="regular_module",
                version="1.0.0",
                folder="managers",
                path=Path("/test"),
                is_mcp=False,
            ),
            ModuleInfo(
                name="mcp_in_managers",
                version="1.0.0",
                folder="managers",
                path=Path("/test"),
                is_mcp=True,
            ),
            ModuleInfo(
                name="mcp_in_mcps",
                version="1.0.0",
                folder="mcps",
                path=Path("/test"),
                is_mcp=True,
            ),
            ModuleInfo(
                name="non_mcp_in_mcps",
                version="1.0.0",
                folder="mcps",
                path=Path("/test"),
                is_mcp=False,
            ),
        ]

    def test_add_mcp_filter(self):
        """add_mcp should add MCP filter."""
        f = ModuleFilter()
        f.add_mcp()
        assert f.has_filters

    def test_mcp_filter_includes_only_mcp_modules(self, modules):
        """MCP filter should only include modules with is_mcp=True."""
        f = ModuleFilter(mode=FilterMode.INCLUDE)
        f.add_mcp()
        
        filtered = f.filter_modules(modules)
        names = {m.name for m in filtered}
        
        assert "mcp_in_managers" in names
        assert "mcp_in_mcps" in names
        assert "regular_module" not in names
        assert "non_mcp_in_mcps" not in names

    def test_mcp_filter_is_independent_of_folder(self, modules):
        """MCP filter should work regardless of folder."""
        f = ModuleFilter(mode=FilterMode.INCLUDE)
        f.add_mcp()
        
        filtered = f.filter_modules(modules)
        
        # Should include MCPs from any folder
        folders = {m.folder for m in filtered}
        assert "managers" in folders
        assert "mcps" in folders


class TestCombinedFiltering:
    """Test combining multiple filter dimensions."""

    @pytest.fixture
    def modules(self) -> list[ModuleInfo]:
        """Create diverse test modules."""
        return [
            ModuleInfo(
                name="foundation_core",
                version="1.0.0",
                folder="cores",
                path=Path("/test"),
                layer=ModuleLayer.FOUNDATION,
                is_mcp=False,
            ),
            ModuleInfo(
                name="runtime_manager",
                version="1.0.0",
                folder="managers",
                path=Path("/test"),
                layer=ModuleLayer.RUNTIME,
                is_mcp=False,
            ),
            ModuleInfo(
                name="dev_mcp",
                version="1.0.0",
                folder="mcps",
                path=Path("/test"),
                layer=ModuleLayer.DEV,
                is_mcp=True,
            ),
            ModuleInfo(
                name="runtime_mcp",
                version="1.0.0",
                folder="mcps",
                path=Path("/test"),
                layer=ModuleLayer.RUNTIME,
                is_mcp=True,
            ),
        ]

    def test_require_mode_needs_all_filters_to_match(self, modules):
        """REQUIRE mode should only match when all filters match (AND logic)."""
        f = ModuleFilter(mode=FilterMode.REQUIRE)
        f.add_folder("mcps")
        f.add_layer("runtime", inherit=False)
        
        filtered = f.filter_modules(modules)
        
        # Only runtime_mcp is in mcps AND has runtime layer
        assert len(filtered) == 1
        assert filtered[0].name == "runtime_mcp"

    def test_include_mode_matches_any_filter(self, modules):
        """INCLUDE mode should match if any filter matches (OR logic)."""
        f = ModuleFilter(mode=FilterMode.INCLUDE)
        f.add_folder("cores")
        f.add_mcp()
        
        filtered = f.filter_modules(modules)
        names = {m.name for m in filtered}
        
        # cores folder OR is_mcp=True
        assert "foundation_core" in names  # in cores
        assert "dev_mcp" in names  # is_mcp
        assert "runtime_mcp" in names  # is_mcp
        assert "runtime_manager" not in names  # neither

    def test_exclude_multiple_criteria(self, modules):
        """EXCLUDE mode should exclude if any filter matches."""
        f = ModuleFilter(mode=FilterMode.EXCLUDE)
        f.add_folder("cores")
        f.add_mcp()
        
        filtered = f.filter_modules(modules)
        names = {m.name for m in filtered}
        
        # Exclude cores AND MCPs
        assert names == {"runtime_manager"}


class TestFilterWithNoFilters:
    """Test behavior when no filters are set."""

    def test_empty_filter_matches_all(self):
        """Filter with no criteria should match all modules."""
        modules = [
            ModuleInfo(name="m1", version="1.0.0", folder="cores", path=Path("/test")),
            ModuleInfo(name="m2", version="1.0.0", folder="managers", path=Path("/test")),
        ]
        
        f = ModuleFilter()
        filtered = f.filter_modules(modules)
        
        assert len(filtered) == 2


class TestFilterInfo:
    """Test FilterInfo helper for available filter values."""

    def test_get_available_returns_all_values(self):
        """get_available should return all valid filter values."""
        info = FilterInfo.get_available()
        
        assert set(info.layers) == {l.value for l in ModuleLayer}
        # Folders include both legacy (cores, managers, etc.) and new (foundation, runtime, dev)
        expected_folders = set(MODULE_FOLDERS) | set(LAYER_SUBFOLDERS)
        assert set(info.folders) == expected_folders
        assert set(info.states) == {s.value for s in GitState}

    def test_format_returns_string(self):
        """format should return a non-empty string."""
        info = FilterInfo.get_available()
        formatted = info.format()
        
        assert isinstance(formatted, str)
        assert len(formatted) > 0
        assert "Layers" in formatted
        assert "Folders" in formatted


class TestAddFilterByDimension:
    """Test the generic add_filter method."""

    def test_add_filter_layer(self):
        """add_filter should work for layer dimension."""
        f = ModuleFilter()
        f.add_filter("layer", "runtime")
        assert f.has_filters

    def test_add_filter_folder(self):
        """add_filter should work for folder dimension."""
        f = ModuleFilter()
        f.add_filter("folder", "managers")
        assert f.has_filters

    def test_add_filter_mcp(self):
        """add_filter should work for mcp dimension."""
        f = ModuleFilter()
        f.add_filter("mcp", "true")
        assert f.has_filters

    def test_add_filter_state(self):
        """add_filter should work for state dimension."""
        f = ModuleFilter()
        f.add_filter("state", "dirty")
        assert f.has_filters

    def test_add_filter_invalid_dimension_raises(self):
        """add_filter should raise for invalid dimension."""
        f = ModuleFilter()
        with pytest.raises(ValueError):
            f.add_filter("invalid", "value")

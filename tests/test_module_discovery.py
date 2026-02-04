"""Tests for folder-based module discovery.

This validates that the new monorepo migration uses folder-based discovery
(cores/, managers/, utils/, plugins/, mcps/) instead of the deprecated
module_type field.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from modules_controller_core import ModulesController, ModuleInfo
from modules_controller_core.module_types import MODULE_FOLDERS, folder_from_path


class TestModuleFolders:
    """Test the MODULE_FOLDERS constant and folder detection."""

    def test_module_folders_contains_expected_folders(self):
        """MODULE_FOLDERS should contain all known module folders."""
        expected = {"cores", "managers", "utils", "plugins", "mcps"}
        assert set(MODULE_FOLDERS) == expected

    def test_module_folders_is_list(self):
        """MODULE_FOLDERS should be a list for deterministic ordering."""
        assert isinstance(MODULE_FOLDERS, list)


class TestFolderFromPath:
    """Test the folder_from_path utility."""

    def test_folder_from_path_with_cores(self, tmp_path: Path):
        """Should extract 'cores' from a module path."""
        root = tmp_path / "project"
        module_path = root / "cores" / "some_core"
        root.mkdir(parents=True)
        module_path.mkdir(parents=True)
        
        folder = folder_from_path(module_path, root)
        assert folder == "cores"

    def test_folder_from_path_with_managers(self, tmp_path: Path):
        """Should extract 'managers' from a module path."""
        root = tmp_path / "project"
        module_path = root / "managers" / "config_manager"
        root.mkdir(parents=True)
        module_path.mkdir(parents=True)
        
        folder = folder_from_path(module_path, root)
        assert folder == "managers"

    def test_folder_from_path_with_mcps(self, tmp_path: Path):
        """Should extract 'mcps' from a module path."""
        root = tmp_path / "project"
        module_path = root / "mcps" / "some_mcp"
        root.mkdir(parents=True)
        module_path.mkdir(parents=True)
        
        folder = folder_from_path(module_path, root)
        assert folder == "mcps"

    def test_folder_from_path_raises_for_unknown(self, tmp_path: Path):
        """Should raise ValueError for paths not in known folders."""
        root = tmp_path / "project"
        module_path = root / "unknown_folder" / "some_module"
        root.mkdir(parents=True)
        module_path.mkdir(parents=True)
        
        with pytest.raises(ValueError, match="Cannot determine module folder"):
            folder_from_path(module_path, root)


class TestModulesControllerDiscovery:
    """Test folder-based module discovery in ModulesController."""

    @pytest.fixture
    def mock_project(self, tmp_path: Path) -> Path:
        """Create a mock project structure with modules in various folders."""
        root = tmp_path / "project"
        
        # Create a manager module
        manager_dir = root / "managers" / "test_manager"
        manager_dir.mkdir(parents=True)
        (manager_dir / "pyproject.toml").write_text("""
[project]
name = "test_manager"
version = "1.0.0"

[tool.adhd]
layer = "runtime"
""")
        (manager_dir / "__init__.py").write_text("")
        
        # Create a core module
        core_dir = root / "cores" / "test_core"
        core_dir.mkdir(parents=True)
        (core_dir / "pyproject.toml").write_text("""
[project]
name = "test_core"
version = "0.5.0"

[tool.adhd]
layer = "foundation"
""")
        (core_dir / "__init__.py").write_text("")
        
        # Create an MCP module with mcp=true flag
        mcp_dir = root / "mcps" / "test_mcp"
        mcp_dir.mkdir(parents=True)
        (mcp_dir / "pyproject.toml").write_text("""
[project]
name = "test_mcp"
version = "2.0.0"

[tool.adhd]
layer = "dev"
mcp = true
""")
        (mcp_dir / "__init__.py").write_text("")
        
        return root

    def test_scan_discovers_modules_by_folder(self, mock_project: Path):
        """Controller should discover modules based on folder structure."""
        controller = ModulesController(root_path=mock_project)
        report = controller.scan_all_modules()
        
        names = {m.name for m in report.modules}
        assert "test_manager" in names
        assert "test_core" in names
        assert "test_mcp" in names

    def test_discovered_modules_have_correct_folder(self, mock_project: Path):
        """Each discovered module should have its folder correctly set."""
        controller = ModulesController(root_path=mock_project)
        report = controller.scan_all_modules()
        
        modules_by_name = {m.name: m for m in report.modules}
        
        assert modules_by_name["test_manager"].folder == "managers"
        assert modules_by_name["test_core"].folder == "cores"
        assert modules_by_name["test_mcp"].folder == "mcps"

    def test_mcp_flag_detected_from_pyproject(self, mock_project: Path):
        """Modules with mcp=true in pyproject.toml should have is_mcp=True."""
        controller = ModulesController(root_path=mock_project)
        report = controller.scan_all_modules()
        
        modules_by_name = {m.name: m for m in report.modules}
        
        assert modules_by_name["test_mcp"].is_mcp is True
        assert modules_by_name["test_manager"].is_mcp is False
        assert modules_by_name["test_core"].is_mcp is False

    def test_skips_directories_without_pyproject(self, mock_project: Path):
        """Should skip directories that don't have pyproject.toml."""
        # Create a directory without pyproject.toml
        (mock_project / "managers" / "not_a_module").mkdir(parents=True)
        
        controller = ModulesController(root_path=mock_project)
        report = controller.scan_all_modules()
        
        names = {m.name for m in report.modules}
        assert "not_a_module" not in names

    def test_skips_hidden_and_dunder_directories(self, mock_project: Path):
        """Should skip hidden (.) and dunder (__) directories."""
        # Create hidden and dunder directories with pyprojects
        hidden_dir = mock_project / "managers" / ".hidden"
        hidden_dir.mkdir(parents=True)
        (hidden_dir / "pyproject.toml").write_text("""
[project]
name = "hidden"
version = "1.0.0"

[tool.adhd]
layer = "runtime"
""")
        
        dunder_dir = mock_project / "managers" / "__pycache__"
        dunder_dir.mkdir(parents=True)
        (dunder_dir / "pyproject.toml").write_text("""
[project]
name = "pycache"
version = "1.0.0"

[tool.adhd]
layer = "runtime"
""")
        
        controller = ModulesController(root_path=mock_project)
        report = controller.scan_all_modules()
        
        names = {m.name for m in report.modules}
        assert ".hidden" not in names
        assert "__pycache__" not in names


class TestModulesControllerCaching:
    """Test module scan caching behavior."""

    @pytest.fixture
    def simple_project(self, tmp_path: Path) -> Path:
        """Create a minimal project structure."""
        root = tmp_path / "project"
        manager_dir = root / "managers" / "cache_test"
        manager_dir.mkdir(parents=True)
        (manager_dir / "pyproject.toml").write_text("""
[project]
name = "cache_test"
version = "1.0.0"

[tool.adhd]
layer = "runtime"
""")
        (manager_dir / "__init__.py").write_text("")
        return root

    def test_list_all_modules_caches_results(self, simple_project: Path):
        """list_all_modules should return cached results on subsequent calls."""
        controller = ModulesController(root_path=simple_project)
        
        # First call - should scan
        report1 = controller.list_all_modules()
        # Second call - should use cache
        report2 = controller.list_all_modules()
        
        assert report1 is report2  # Same object reference

    def test_scan_all_modules_refreshes_cache(self, simple_project: Path):
        """scan_all_modules should always rescan and refresh cache."""
        controller = ModulesController(root_path=simple_project)
        
        report1 = controller.scan_all_modules()
        report2 = controller.scan_all_modules()
        
        # Different objects, but same content
        assert report1 is not report2
        assert len(report1.modules) == len(report2.modules)

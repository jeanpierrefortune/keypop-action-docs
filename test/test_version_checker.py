import pytest
from unittest.mock import Mock, patch, mock_open
from pathlib import Path
import subprocess
from doxygen.scripts.check_version import VersionChecker, VersionError

@pytest.fixture
def checker():
    return VersionChecker()

@pytest.fixture
def mock_cmake_content():
    return '''
    CMAKE_MINIMUM_REQUIRED(VERSION 3.0)
    
    PROJECT(TestProject VERSION 1.2.3)
    
    SET(RC_VERSION "1")
    '''

class TestVersionChecker:
    def test_validate_version_valid_formats(self, checker):
        """Test version validation with valid version formats"""
        assert checker.validate_version("1.2.3")
        assert checker.validate_version("0.0.1")
        assert checker.validate_version("10.20.30")
        assert checker.validate_version("1.2.3-rc1")

    def test_validate_version_invalid_formats(self, checker):
        """Test version validation with invalid version formats"""
        assert not checker.validate_version("1.2")
        assert not checker.validate_version("1.2.3.4")
        assert not checker.validate_version("1.2.3-alpha1")
        assert not checker.validate_version("invalid")
        assert not checker.validate_version("")

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    def test_parse_cmake_version(self, mock_read_text, mock_exists, checker, mock_cmake_content):
        """Test CMake version parsing"""
        mock_exists.return_value = True
        mock_read_text.return_value = mock_cmake_content
        
        version = checker._parse_cmake_version(Path("CMakeLists.txt"))
        assert version == "1.2.3-rc1"

    @patch('pathlib.Path.exists')
    def test_parse_cmake_version_missing_file(self, mock_exists, checker):
        """Test error handling for missing CMakeLists.txt"""
        mock_exists.return_value = False
        
        with pytest.raises(FileNotFoundError):
            checker._parse_cmake_version(Path("CMakeLists.txt"))

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    def test_parse_cmake_version_invalid_content(self, mock_read_text, mock_exists, checker):
        """Test error handling for invalid CMake content"""
        mock_exists.return_value = True
        mock_read_text.return_value = "Invalid CMake content"
        
        with pytest.raises(VersionError):
            checker._parse_cmake_version(Path("CMakeLists.txt"))

    @patch('subprocess.run')
    def test_run_git_command_success(self, mock_run, checker):
        """Test successful git command execution"""
        mock_run.return_value = Mock(stdout="v1.2.3\n", returncode=0)
        
        result = checker._run_git_command(["describe", "--tags"])
        assert result == "v1.2.3"

    @patch('subprocess.run')
    def test_run_git_command_failure(self, mock_run, checker):
        """Test git command failure"""
        mock_run.side_effect = subprocess.CalledProcessError(1, "git", "error")
        
        with pytest.raises(subprocess.CalledProcessError):
            checker._run_git_command(["describe", "--tags"])

    @patch.object(VersionChecker, '_parse_cmake_version')
    @patch.object(VersionChecker, '_run_git_command')
    def test_check_version_tag_match(self, mock_git, mock_parse, checker):
        """Test version checking with matching tag"""
        mock_parse.return_value = "1.2.3"
        
        checker.check_version("1.2.3")
        # Should not raise any exception

    @patch.object(VersionChecker, '_parse_cmake_version')
    @patch.object(VersionChecker, '_run_git_command')
    def test_check_version_tag_mismatch(self, mock_git, mock_parse, checker):
        """Test version checking with mismatched tag"""
        mock_parse.return_value = "1.2.3"
        
        with pytest.raises(SystemExit):
            checker.check_version("1.2.4")

    @patch.object(VersionChecker, '_parse_cmake_version')
    @patch.object(VersionChecker, '_run_git_command')
    def test_check_version_existing_version(self, mock_git, mock_parse, checker):
        """Test version checking with already existing version"""
        mock_parse.return_value = "1.2.3"
        mock_git.return_value = "1.2.3"
        
        with pytest.raises(SystemExit):
            checker.check_version(None)

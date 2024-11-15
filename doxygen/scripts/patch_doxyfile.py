#!/usr/bin/env python3

import argparse
import re
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class VersionError(Exception):
    """Custom exception for version-related errors"""
    pass

class DoxyfileUpdater:
    def __init__(self):
        self.version_pattern = re.compile(r'^\d+\.\d+\.\d+(?:-rc\d+)?(?:-SNAPSHOT)?$')

    def validate_version(self, version: str) -> bool:
        """Validate version string format"""
        return bool(self.version_pattern.match(version))

    def _parse_cmake_version(self, cmake_file: Path) -> str:
        """
        Extract version from CMakeLists.txt

        Args:
            cmake_file: Path to CMakeLists.txt

        Returns:
            str: Version string in format X.Y.Z[-rcN][-SNAPSHOT]

        Raises:
            FileNotFoundError: If CMakeLists.txt doesn't exist
            VersionError: If version cannot be extracted
        """
        if not cmake_file.exists():
            raise FileNotFoundError(f"CMakeLists.txt not found at {cmake_file}")

        content = cmake_file.read_text()

        project_version_pattern = r'PROJECT\s*\([^)]*VERSION\s+(\d+\.\d+\.\d+)[^)]*\)'
        version_match = re.search(project_version_pattern, content, re.MULTILINE | re.IGNORECASE)

        if not version_match:
            raise VersionError("Could not extract PROJECT VERSION")

        version = version_match.group(1)

        # Look for RC version
        rc_pattern = r'^[^#]*SET\s*\(RC_VERSION\s*"(\d+)"\s*\)'
        rc_match = re.search(rc_pattern, content, re.MULTILINE)

        if rc_match:
            version = f"{version}-rc{rc_match.group(1)}"
        else:
            # Check if this is a release version
            package_pattern = r'SET\s*\(PACKAGE_VERSION\s*"\$\{PROJECT_VERSION\}"\s*\)'
            is_release = bool(re.search(package_pattern, content, re.MULTILINE))

            if not is_release:
                version = f"{version}-SNAPSHOT"

        if not self.validate_version(version):
            raise VersionError(f"Invalid version format: {version}")

        return version

    def update_doxyfile(self, doxyfile_path: Path, version: Optional[str] = None) -> None:
        """
        Update Doxyfile with current version

        Args:
            doxyfile_path: Path to the Doxyfile
            version: Optional version string, if not provided will be extracted from CMakeLists.txt

        Raises:
            FileNotFoundError: If Doxyfile doesn't exist
            VersionError: If version is invalid or cannot be extracted
        """
        logger.info("Computing current API version...")

        if version and not self.validate_version(version):
            raise VersionError(f"Invalid version format: {version}")

        if not version:
            version = self._parse_cmake_version(Path("CMakeLists.txt"))

        logger.info(f"Using API version: {version}")

        if not doxyfile_path.exists():
            raise FileNotFoundError(f"Doxyfile not found at {doxyfile_path}")

        try:
            content = doxyfile_path.read_text()
            updated_content = content.replace("%PROJECT_VERSION%", version)
            doxyfile_path.write_text(updated_content)
            logger.info(f"Updated {doxyfile_path} with version {version}")
        except IOError as e:
            raise IOError(f"Failed to update Doxyfile: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update Doxyfile version")
    parser.add_argument("doxyfile_path", type=Path, help="Path to the Doxyfile")
    parser.add_argument("version", nargs="?", help="Version to set (optional)")
    args = parser.parse_args()

    try:
        updater = DoxyfileUpdater()
        updater.update_doxyfile(args.doxyfile_path, args.version)
    except Exception as e:
        logger.error(str(e))
        raise SystemExit(1)
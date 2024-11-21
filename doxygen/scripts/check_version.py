#!/usr/bin/env python3

import argparse
import re
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple
from packaging.version import parse, Version

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class VersionError(Exception):
    """Custom exception for version-related errors"""
    pass

class VersionChecker:
    def __init__(self):
        # Base version (Java reference) pattern x.y.z
        self.java_version_pattern = re.compile(r'^\d+\.\d+\.\d+$')
        # Full version pattern (with optional C++ fix) x.y.z[.t]
        self.version_pattern = re.compile(r'^\d+\.\d+\.\d+(?:\.\d+)?$')
        # Pattern to extract the C++ fix number
        self.cpp_fix_pattern = re.compile(r'^\d+\.\d+\.\d+\.(\d+)$')

    def validate_version(self, version: str) -> bool:
        """Validate version string format"""
        return bool(self.version_pattern.match(version))

    def split_version(self, version: str) -> Tuple[str, Optional[str]]:
        """Split version into Java reference version and C++ fix number"""
        if not self.validate_version(version):
            raise VersionError(f"Invalid version format: {version}")

        cpp_fix_match = self.cpp_fix_pattern.match(version)
        if cpp_fix_match:
            # Split into Java version and C++ fix
            java_version = version.rsplit('.', 1)[0]
            cpp_fix = cpp_fix_match.group(1)
            return java_version, cpp_fix
        return version, None

    def _parse_cmake_version(self, cmake_file: Path) -> str:
        """
        Extract base version from CMakeLists.txt

        Args:
            cmake_file: Path to CMakeLists.txt

        Returns:
            str: Version string in format X.Y.Z[.T] (Java reference version with optional C++ fix)

        Raises:
            FileNotFoundError: If CMakeLists.txt doesn't exist
            VersionError: If version cannot be extracted
        """
        if not cmake_file.exists():
            raise FileNotFoundError(f"CMakeLists.txt not found at {cmake_file}")

        content = cmake_file.read_text()

        # Updated pattern to capture optional fourth number
        project_version_pattern = r'PROJECT\s*\([^)]*VERSION\s+(\d+\.\d+\.\d+(?:\.\d+)?)[^)]*\)'
        version_match = re.search(project_version_pattern, content, re.MULTILINE | re.IGNORECASE)

        if not version_match:
            raise VersionError("Could not extract PROJECT VERSION")

        version = version_match.group(1)
        if not self.version_pattern.match(version):
            raise VersionError(f"Invalid version format in CMakeLists.txt: {version}")

        return version

    def _run_git_command(self, args: list) -> str:
        """
        Run git command safely

        Raises:
            subprocess.CalledProcessError: If command fails
        """
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()

    def check_version(self, tag: Optional[str] = None) -> None:
        """
        Check version consistency between CMakeLists.txt and git tag

        Args:
            tag: Optional git tag to check against

        Raises:
            VersionError: If versions don't match or version already exists
        """
        try:
            cmake_version = self._parse_cmake_version(Path("CMakeLists.txt"))
            cmake_java_version, cmake_cpp_fix = self.split_version(cmake_version)
            logger.info(f"Version in CMakeLists.txt: '{cmake_version}' (Java: {cmake_java_version}"
                        f"{f', C++ fix: {cmake_cpp_fix}' if cmake_cpp_fix else ''})")

            if tag:
                if not self.validate_version(tag):
                    raise VersionError(f"Invalid tag format: {tag}")

                logger.info(f"Input tag: '{tag}'")
                logger.info("Release mode: checking version consistency...")

                tag_java_version, tag_cpp_fix = self.split_version(tag)
                if tag_java_version != cmake_java_version:
                    raise VersionError(
                        f"Tag Java version '{tag_java_version}' differs from version '{cmake_java_version}' in CMakeLists.txt"
                    )
                if tag_cpp_fix != cmake_cpp_fix:
                    raise VersionError(
                        f"Tag C++ fix version '{tag_cpp_fix}' differs from version '{cmake_cpp_fix}' in CMakeLists.txt"
                    )
                logger.info(f"Version consistency check passed: '{tag}'")
            else:
                logger.info("Snapshot mode: fetching tags...")
                self._run_git_command(["fetch", "--tags"])

                # Check if any version with this Java reference exists
                existing_tags = self._run_git_command(["tag", "-l", f"{cmake_java_version}*"]).split('\n')
                if existing_tags and any(tag.strip() for tag in existing_tags):
                    if cmake_cpp_fix:
                        # For C++ fixes, check if this specific fix version exists
                        if cmake_version in existing_tags:
                            raise VersionError(f"Version '{cmake_version}' already released")
                    else:
                        raise VersionError(f"Java reference version '{cmake_java_version}' or its C++ fixes already released")
                logger.info(f"Version '{cmake_version}' not yet released")

        except (subprocess.CalledProcessError, FileNotFoundError, VersionError) as e:
            logger.error(str(e))
            raise SystemExit(1)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise SystemExit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check version consistency")
    parser.add_argument("tag", nargs="?", help="Git tag to check against (optional)")
    args = parser.parse_args()

    checker = VersionChecker()
    checker.check_version(args.tag)
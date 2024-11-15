#!/usr/bin/env python3

import argparse
import re
import subprocess
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

class VersionChecker:
    def __init__(self):
        self.version_pattern = re.compile(r'^\d+\.\d+\.\d+(?:-rc\d+)?$')

    def validate_version(self, version: str) -> bool:
        """Validate version string format"""
        return bool(self.version_pattern.match(version))

    def _parse_cmake_version(self, cmake_file: Path) -> str:
        """
        Extract version from CMakeLists.txt

        Args:
            cmake_file: Path to CMakeLists.txt

        Returns:
            str: Version string in format X.Y.Z or X.Y.Z-rcN

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

        rc_version = self._extract_rc_version(content)
        if rc_version:
            version = f"{version}-rc{rc_version}"

        if not self.validate_version(version):
            raise VersionError(f"Invalid version format: {version}")

        return version

    def _extract_rc_version(self, content: str) -> Optional[str]:
        """Extract RC version if present"""
        rc_pattern = r'^[^#]*SET\s*\((?:RC_VERSION|CMAKE_PROJECT_VERSION_RC)\s*"(\d+)"\s*\)'
        rc_match = re.search(rc_pattern, content, re.MULTILINE)
        return rc_match.group(1) if rc_match else None

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
            version = self._parse_cmake_version(Path("CMakeLists.txt"))
            logger.info(f"Version in CMakeLists.txt: '{version}'")

            if tag:
                if not self.validate_version(tag):
                    raise VersionError(f"Invalid tag format: {tag}")

                logger.info(f"Input tag: '{tag}'")
                logger.info("Release mode: checking version consistency...")

                if tag != version:
                    raise VersionError(
                        f"Tag '{tag}' differs from version '{version}' in CMakeLists.txt"
                    )
                logger.info(f"Version consistency check passed: '{tag}'")
            else:
                logger.info("Snapshot mode: fetching tags...")
                self._run_git_command(["fetch", "--tags"])

                existing_tag = self._run_git_command(["tag", "-l", version])
                if existing_tag:
                    raise VersionError(f"Version '{version}' already released")
                logger.info(f"Version '{version}' not yet released")

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
#!/usr/bin/env python3

import argparse
import re
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple

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
        self.base_version_pattern = re.compile(r'^\d+\.\d+\.\d+$')
        self.rc_pattern = re.compile(r'-rc(\d+)$')

    def validate_version(self, version: str) -> bool:
        """Validate version string format"""
        return bool(self.version_pattern.match(version))

    def split_version(self, version: str) -> Tuple[str, Optional[str]]:
        """Split version into base version and RC number"""
        if not self.validate_version(version):
            raise VersionError(f"Invalid version format: {version}")

        rc_match = self.rc_pattern.search(version)
        if rc_match:
            base_version = version[:rc_match.start()]
            rc_num = rc_match.group(1)
            return base_version, rc_num
        return version, None

    def _parse_cmake_version(self, cmake_file: Path) -> str:
        """
        Extract base version from CMakeLists.txt

        Args:
            cmake_file: Path to CMakeLists.txt

        Returns:
            str: Version string in format X.Y.Z

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
        if not self.base_version_pattern.match(version):
            raise VersionError(f"Invalid base version format in CMakeLists.txt: {version}")

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
            logger.info(f"Base version in CMakeLists.txt: '{cmake_version}'")

            if tag:
                if not self.validate_version(tag):
                    raise VersionError(f"Invalid tag format: {tag}")

                logger.info(f"Input tag: '{tag}'")
                logger.info("Release mode: checking version consistency...")

                tag_base, tag_rc = self.split_version(tag)
                if tag_base != cmake_version:
                    raise VersionError(
                        f"Tag base version '{tag_base}' differs from version '{cmake_version}' in CMakeLists.txt"
                    )
                logger.info(f"Version consistency check passed: '{tag}'")
            else:
                logger.info("Snapshot mode: fetching tags...")
                self._run_git_command(["fetch", "--tags"])

                # Check if any version (base or RC) exists
                existing_tags = self._run_git_command(["tag", "-l", f"{cmake_version}*"]).split('\n')
                if existing_tags and any(tag.strip() for tag in existing_tags):
                    raise VersionError(f"Version '{cmake_version}' or its release candidates already released")

                # Add SNAPSHOT suffix for logging
                snapshot_version = f"{cmake_version}-SNAPSHOT"
                logger.info(f"Version '{snapshot_version}' not yet released")

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
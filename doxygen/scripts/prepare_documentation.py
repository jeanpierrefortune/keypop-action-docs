#!/usr/bin/env python3

import argparse
import os
import re
import shutil
import subprocess
import logging
import fcntl
from pathlib import Path
from packaging.version import parse, Version, InvalidVersion

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DocumentationManager:
    def __init__(self, github_org: str, repo_name: str):
        self.repo_url = f"https://github.com/{github_org}/{repo_name}.git"
        self.gh_pages_branch = "gh-pages"
        self.version_pattern = re.compile(r'^\d+\.\d+\.\d+(?:\.\d+)?(?:-SNAPSHOT)?$')
        self.java_version_pattern = re.compile(r'^\d+\.\d+\.\d+$')
        self.lock_file = Path("/tmp/doc_manager.lock")

    def _get_version_key(self, version_str: str) -> tuple:
        """
        Create a sortable key for version ordering that maintains the following order:
        1. SNAPSHOT versions first (by Java version, then C++ fix)
        2. Regular versions (by Java version, then C++ fix, newest first)

        Returns tuple of (major, minor, patch, cpp_fix, is_snapshot)
        """
        try:
            # Remove snapshot suffix for parsing
            is_snapshot = "-SNAPSHOT" in version_str
            clean_version = version_str.replace("-SNAPSHOT", "")

            # Split into components
            if "." in clean_version:
                *java_parts, cpp_fix = clean_version.split(".")
                java_version = ".".join(java_parts)
                cpp_fix = int(cpp_fix)
            else:
                java_version = clean_version
                cpp_fix = 0

            v = parse(java_version)

            # is_snapshot is first element for snapshot-first sorting
            return (not is_snapshot, v.major, v.minor, v.micro, cpp_fix)

        except (InvalidVersion, ValueError, IndexError):
            # En cas d'erreur de parsing, mettre la version en dernier
            return (True, 0, 0, 0, 0)

    # [... autres méthodes de DocumentationManager inchangées ...]

    def _generate_versions_list(self, docs_dir: Path):
        """Generate the versions list markdown file"""
        versions_file = Path("list_versions.md")

        logger.info("Looking for version directories")
        versions = []
        for d in Path('.').glob('*'):
            if d.is_dir() and self.version_pattern.match(d.name):
                logger.info(f"Found version directory: {d.name}")
                versions.append(d.name)
            elif d.is_dir():
                logger.debug(f"Skipping non-version directory: {d.name}")

        sorted_versions = sorted(versions, key=self._get_version_key)
        logger.debug(f"Sorted versions: {sorted_versions}")

        # Find the latest stable version (first non-SNAPSHOT version without C++ fix)
        latest_stable = next((v for v in sorted_versions
                              if "-SNAPSHOT" not in v and len(v.split('.')) == 3), None)

        with versions_file.open("w") as f:
            f.write("| Version | Documents |\n")
            f.write("|:---:|---|\n")

            for version in sorted_versions:
                # Write latest-stable first if this is the stable version
                if version == latest_stable:
                    f.write(f"| latest-stable ({latest_stable}) | [API documentation](latest-stable) |\n")

                # Write the current version
                f.write(f"| {version} | [API documentation]({version}) |\n")

    def _get_version_key(self, version_str: str) -> tuple:
        """
        Create a sortable key for version ordering that maintains the following order:
        1. SNAPSHOT versions first
        2. RC versions (newest RC first)
        3. Release versions

        Returns tuple of (major, minor, patch, version_type, rc_num)
        version_type: 2 for SNAPSHOT, 1 for RC, 0 for release
        """
        try:
            # Split version into parts
            if "-rc" in version_str:
                base_version = version_str.split("-rc")[0]
                rc_part = version_str.split("-rc")[1]
                rc_num = int(rc_part.split("-")[0]) if "-" not in rc_part else int(rc_part.split("-SNAPSHOT")[0])
                is_snapshot = "-SNAPSHOT" in version_str
            else:
                base_version = version_str.split("-")[0]
                rc_num = 0
                is_snapshot = "-SNAPSHOT" in version_str

            v = parse(base_version)

            # Determine version type
            # 2 for SNAPSHOT (highest priority), 1 for RC, 0 for release (lowest priority)
            if is_snapshot:
                version_type = 2
            elif rc_num > 0:
                version_type = 1
            else:
                version_type = 0

            return (v.major, v.minor, v.micro, version_type, rc_num)

        except (InvalidVersion, ValueError, IndexError):
            # En cas d'erreur de parsing, mettre la version en dernier
            return (0, 0, 0, -1, 0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare API documentation")
    parser.add_argument("--github-org", required=True, help="GitHub organization name")
    parser.add_argument("--repo-name", required=True, help="Repository name")
    parser.add_argument("--version", help="Version to publish (optional)")
    args = parser.parse_args()

    try:
        manager = DocumentationManager(args.github_org, args.repo_name)
        manager.prepare_documentation(args.version)
    except Exception as e:
        logger.error(f"Documentation preparation failed: {e}")
        raise
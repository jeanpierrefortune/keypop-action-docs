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
        self.version_pattern = re.compile(r'^\d+\.\d+\.\d+(?:\.\d+)?$')
        self.java_version_pattern = re.compile(r'^\d+\.\d+\.\d+$')
        self.lock_file = Path("/tmp/doc_manager.lock")

    def _acquire_lock(self):
        """Acquire a file lock to prevent concurrent directory operations"""
        self.lock_fd = open(self.lock_file, 'w')
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another documentation process is running")

    def _release_lock(self):
        """Release the file lock"""
        fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
        self.lock_fd.close()

    def _parse_cmake_version(self, cmake_file: Path) -> str:
        """
        Extract base version from CMakeLists.txt

        Args:
            cmake_file: Path to CMakeLists.txt

        Returns:
            str: Version string in format X.Y.Z

        Raises:
            ValueError: If version cannot be extracted
            FileNotFoundError: If CMakeLists.txt doesn't exist
        """
        if not cmake_file.exists():
            raise FileNotFoundError(f"CMakeLists.txt not found at {cmake_file}")

        content = cmake_file.read_text()

        project_version_pattern = r'PROJECT\s*\([^)]*VERSION\s+(\d+\.\d+\.\d+)[^)]*\)'
        version_match = re.search(project_version_pattern, content, re.MULTILINE | re.IGNORECASE)

        if not version_match:
            raise ValueError("Could not extract PROJECT VERSION")

        version = version_match.group(1)
        if not self.java_version_pattern.match(version):
            raise ValueError(f"Invalid Java reference version format in CMakeLists.txt: {version}")

        # Check for C++ fix version
        cpp_fix_pattern = r'SET\s*\(VERSION_CPPFIX\s*"(\d+)"\s*\)'
        cpp_fix_match = re.search(cpp_fix_pattern, content)

        if cpp_fix_match:
            version = f"{version}.{cpp_fix_match.group(1)}"

        return version

    def _get_version_key(self, version_str: str) -> tuple:
        """
        Create a sortable key for version ordering that maintains the following order:
        1. SNAPSHOT versions first (by Java version, then C++ fix)
        2. Regular versions (by Java version, then C++ fix, newest first)

        Returns tuple of (major, minor, patch, cpp_fix, is_snapshot)
        """
        try:
            is_snapshot = "-SNAPSHOT" in version_str
            clean_version = version_str.replace("-SNAPSHOT", "")

            # Parse version number components
            if "." in clean_version:
                *java_parts, cpp_fix = clean_version.split(".")
                java_version = ".".join(java_parts)
                cpp_fix = int(cpp_fix)
            else:
                java_version = clean_version
                cpp_fix = 0

            v = parse(java_version)

            # Use negative values to reverse chronological order while keeping SNAPSHOT first
            return (not is_snapshot, -v.major, -v.minor, -v.micro, -cpp_fix)

        except (InvalidVersion, ValueError, IndexError):
            # Return a default tuple in case of parsing error
            return (True, 0, 0, 0, 0)

    def _safe_copy(self, src: Path, dest: Path) -> None:
        """
        Safely copy files ensuring no path traversal vulnerability

        Raises:
            ValueError: If path traversal is detected
        """
        try:
            src = src.resolve()
            dest = dest.resolve()
            if not str(src).startswith(str(src.parent.resolve())):
                raise ValueError(f"Potential path traversal detected: {src}")
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dest)
        except Exception as e:
            logger.error(f"Error copying {src} to {dest}: {e}")
            raise

    def _remove_snapshots(self):
        """Remove all SNAPSHOT directories"""
        logger.info("Processing SNAPSHOT directories...")
        for d in Path('.').glob('*-SNAPSHOT'):
            logger.info(f"Removing SNAPSHOT directory: {d}")
            if d.is_dir():
                shutil.rmtree(d)
            else:
                d.unlink()

    def _generate_versions_list(self, docs_dir: Path):
        """Generate the versions list markdown file"""
        versions_file = Path("list_versions.md")

        logger.info("Looking for version directories")
        versions = []
        for d in Path('.').glob('*'):
            if d.is_dir() and (self.version_pattern.match(d.name) or d.name.endswith("-SNAPSHOT")):
                logger.info(f"Found version directory: {d.name}")
                versions.append(d.name)
            elif d.is_dir():
                logger.debug(f"Skipping non-version directory: {d.name}")

        sorted_versions = sorted(versions, key=self._get_version_key)
        logger.debug(f"Sorted versions: {sorted_versions}")

        # Find the latest stable version (first non-SNAPSHOT version)
        latest_stable = next((v for v in sorted_versions if "-SNAPSHOT" not in v), None)

        with versions_file.open("w") as f:
            f.write("| Version | Documents |\n")
            f.write("|:---:|---|\n")

            for version in sorted_versions:
                # Write latest-stable first if this is the stable version
                if version == latest_stable:
                    f.write(f"| latest-stable ({latest_stable}) | [API documentation](latest-stable) |\n")

                # Write the current version
                f.write(f"| {version} | [API documentation]({version}) |\n")

    def prepare_documentation(self, version: str = None):
        """
        Main method to prepare documentation

        Args:
            version: Version string (tag version for release, or base version for snapshots)

        Raises:
            ValueError: If version is invalid
            RuntimeError: If another process is running
            FileNotFoundError: If required files are missing
        """
        try:
            self._acquire_lock()

            if version:
                if not self.version_pattern.match(version):
                    raise ValueError(f"Invalid tag format: {version}")
                version_to_use = version
                is_snapshot = False
            else:
                # Use base version from CMakeLists.txt with -SNAPSHOT suffix
                base_version = self._parse_cmake_version(Path("CMakeLists.txt"))
                version_to_use = f"{base_version}-SNAPSHOT"
                is_snapshot = True

            logger.info(f"Using version: {version_to_use}")

            repo_name = Path.cwd().name
            dest_dir = Path(repo_name)

            logger.info(f"Clone {repo_name}...")
            if dest_dir.exists():
                shutil.rmtree(dest_dir)

            subprocess.run(["git", "clone", "-b", self.gh_pages_branch, self.repo_url, repo_name],
                           check=True, capture_output=True)

            os.chdir(dest_dir)

            # For releases, remove all SNAPSHOT directories before creating the new version
            if not is_snapshot:
                self._remove_snapshots()

            logger.info(f"Create target directory {version_to_use}...")
            version_dir = Path(version_to_use)
            version_dir.mkdir(exist_ok=True)

            logger.info("Copy Doxygen doc...")
            doxygen_out = Path("../.github/doxygen/out/html")
            if not doxygen_out.exists():
                raise FileNotFoundError(f"Doxygen output directory not found at {doxygen_out}")

            for item in doxygen_out.glob("*"):
                self._safe_copy(item, version_dir / item.name)

                # Create latest-stable symlink for any final release (including C++ fixes)
            if not is_snapshot:
                logger.info("Creating latest-stable symlink...")
                latest_link = Path("latest-stable")
                if latest_link.exists():
                    if latest_link.is_dir():
                        logger.info(f"Removing latest-stable directory: {latest_link}")
                        shutil.rmtree(latest_link)
                    else:
                        latest_link.unlink()
                latest_link.symlink_to(version_to_use)

                logger.info("Writing robots.txt...")
                robots_txt = Path("robots.txt")
                robots_txt.write_text(
                    "User-agent: *\n"
                    "Allow: /\n"
                    "Allow: /latest-stable/\n"
                    "Disallow: /*/[0-9]*/\n"
                )

            logger.info("Generating versions list...")
            self._generate_versions_list(Path('.'))

            os.chdir("..")

        finally:
            self._release_lock()

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
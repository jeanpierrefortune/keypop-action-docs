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
        self.version_pattern = re.compile(r'^\d+\.\d+\.\d+(?:-rc\d+)?(?:-SNAPSHOT)?$')
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

    def validate_version(self, version: str) -> bool:
        """
        Validate version string format.
        Returns True if version matches expected pattern.
        """
        if not isinstance(version, str):
            return False
        return bool(self.version_pattern.match(version))

    def _parse_cmake_version(self, cmake_file: Path) -> str:
        """
        Extract version from CMakeLists.txt
        Handles both PROJECT VERSION and RC_VERSION

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

        rc_pattern = r'^[^#]*SET\s*\(RC_VERSION\s*"(\d+)"\s*\)'
        rc_match = re.search(rc_pattern, content, re.MULTILINE)

        if rc_match:
            return f"{version}-rc{rc_match.group(1)}-SNAPSHOT"
        return f"{version}-SNAPSHOT"

    def _get_version_key(self, version_str: str) -> tuple:
        """
        Create a sortable key for version ordering that maintains the following order:
        1. RC SNAPSHOT versions (newest RC first)
        2. RC released versions
        3. Base SNAPSHOT version

        Returns tuple of (major, minor, patch, version_type, rc_num)
        """
        try:
            base_version = version_str.split('-')[0]
            v = parse(base_version)
            base = (v.major, v.minor, v.micro)

            if "rc" in version_str.lower():
                rc_num = int(version_str.lower().split("rc")[1].split("-")[0])
                if "SNAPSHOT" in version_str:
                    return base + (2, rc_num)
                return base + (1, rc_num)
            if "SNAPSHOT" in version_str:
                return base + (0, 0)
            return base + (3, 0)

        except InvalidVersion:
            return (0, 0, 0, 999, 0)

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

    def prepare_documentation(self, version: str = None):
        """
        Main method to prepare documentation

        Args:
            version: Optional version string. If not provided, extracted from CMakeLists.txt

        Raises:
            ValueError: If version is invalid
            RuntimeError: If another process is running
            FileNotFoundError: If required files are missing
        """
        try:
            self._acquire_lock()

            if not version:
                version = self._parse_cmake_version(Path("CMakeLists.txt"))

            if not self.validate_version(version):
                raise ValueError(f"Invalid version format: {version}")

            logger.info(f"Using version: {version}")

            repo_name = Path.cwd().name
            dest_dir = Path(repo_name)

            logger.info(f"Clone {repo_name}...")
            if dest_dir.exists():
                shutil.rmtree(dest_dir)

            subprocess.run(["git", "clone", "-b", self.gh_pages_branch, self.repo_url, repo_name],
                         check=True, capture_output=True)

            os.chdir(dest_dir)

            logger.info("Processing SNAPSHOT directories...")
            if not version.endswith("-SNAPSHOT"):
                if "-rc" in version:
                    rc_snapshot = f"{version}-SNAPSHOT"
                    snapshot_path = Path(rc_snapshot)
                    if snapshot_path.exists():
                        logger.info(f"Removing RC SNAPSHOT directory: {snapshot_path}")
                        shutil.rmtree(snapshot_path)
                else:
                    version_snapshot = f"{version}-SNAPSHOT"
                    snapshot_path = Path(version_snapshot)
                    if snapshot_path.exists():
                        logger.info(f"Removing version SNAPSHOT directory: {snapshot_path}")
                        shutil.rmtree(snapshot_path)

            logger.info(f"Create target directory {version}...")
            version_dir = Path(version)
            version_dir.mkdir(exist_ok=True)

            logger.info("Copy Doxygen doc...")
            doxygen_out = Path("../.github/doxygen/out/html")
            if not doxygen_out.exists():
                raise FileNotFoundError(f"Doxygen output directory not found at {doxygen_out}")

            for item in doxygen_out.glob("*"):
                self._safe_copy(item, version_dir / item.name)

            if not any(x in version for x in ["-SNAPSHOT", "-rc"]):
                logger.info("Creating latest-stable symlink...")
                latest_link = Path("latest-stable")
                if latest_link.exists():
                    if latest_link.is_dir():
                        logger.info(f"Removing latest-stable directory: {latest_link}")
                        shutil.rmtree(latest_link)
                    else:
                        latest_link.unlink()
                latest_link.symlink_to(version)

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

        sorted_versions = sorted(versions, key=self._get_version_key, reverse=True)
        logger.debug(f"Sorted versions: {sorted_versions}")

        # Find the latest stable version (first non-SNAPSHOT, non-RC version)
        latest_stable = next((v for v in sorted_versions if "-SNAPSHOT" not in v and "-rc" not in v), None)

        with versions_file.open("w") as f:
            f.write("| Version | Documents |\n")
            f.write("|:---:|---|\n")

            for version in sorted_versions:
                # If this is the stable version and we haven't written it yet
                if version == latest_stable:
                    # Write latest-stable first
                    f.write(f"| latest-stable ({latest_stable}) | [API documentation](latest-stable) |\n")

                # Write the current version
                f.write(f"| {version} | [API documentation]({version}) |\n")

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
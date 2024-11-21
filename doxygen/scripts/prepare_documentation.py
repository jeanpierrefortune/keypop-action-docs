#!/usr/bin/env python3

import argparse
import os
import re
import shutil
import subprocess
import logging
import fcntl
from pathlib import Path
from packaging.version import parse

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
        """Extract version from CMakeLists.txt"""
        if not cmake_file.exists():
            raise FileNotFoundError(f"CMakeLists.txt not found at {cmake_file}")

        content = cmake_file.read_text()
        version_match = re.search(r'PROJECT\s*\([^)]*VERSION\s+(\d+\.\d+\.\d+(?:\.\d+)?)[^)]*\)',
                                  content, re.MULTILINE | re.IGNORECASE)

        if not version_match:
            raise ValueError("Could not extract PROJECT VERSION")
        return version_match.group(1)

    def _get_version_key(self, version_str: str) -> tuple:
        """
        Create a sortable key for version ordering that maintains the following order:
        1. SNAPSHOT versions first
        2. Regular versions in semantic version order (newest first)
        3. C++ fix versions are treated as an extension of the patch version

        Returns tuple of (is_snapshot, -major, -minor, -patch, -cpp_fix)
        where negative values are used to sort in descending order
        """
        try:
            is_snapshot = "-SNAPSHOT" in version_str
            clean_version = version_str.replace("-SNAPSHOT", "")

            # Split version components
            parts = clean_version.split(".")

            # Parse components with defaults
            major = int(parts[0]) if len(parts) > 0 else 0
            minor = int(parts[1]) if len(parts) > 1 else 0
            patch = int(parts[2]) if len(parts) > 2 else 0
            cpp_fix = int(parts[3]) if len(parts) > 3 else 0

            # Use negative values to sort in descending order
            # Not is_snapshot comes first to keep snapshots at the top
            return (not is_snapshot, -major, -minor, -patch, -cpp_fix)

        except Exception as e:
            logger.error(f"Error parsing version {version_str}: {e}")
            # Return a default tuple that will sort to the end
            return (True, 0, 0, 0, 0)

    def _safe_copy(self, src: Path, dest: Path) -> None:
        """Safely copy files ensuring no path traversal vulnerability"""
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
                f.write(f"| {version} | [API documentation]({version}) |\n")

    def prepare_documentation(self, version: str = None):
        """
        Main method to prepare documentation

        Args:
            version: Version string (tag version for release, or base version for snapshots)
        """
        try:
            self._acquire_lock()

            if version:
                version_to_use = version
                is_snapshot = False
            else:
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

            # For releases, remove all SNAPSHOT directories
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
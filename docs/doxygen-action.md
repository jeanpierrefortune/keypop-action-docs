# Keypop Doxygen Documentation Action

Action for generating and publishing C++ API reference documentation using Doxygen. This action handles versioning,
navigation between versions, and proper organization of documentation artifacts.

#### Features

- **Automatic Version Detection**: Extracts version information from `CMakeLists.txt`
- **Version Management**:
    - Supports release versions (X.Y.Z)
    - Handles release candidates (X.Y.Z-rcN)
    - Manages development versions (X.Y.Z-SNAPSHOT)
- **Documentation Organization**:
    - Creates versioned documentation directories
    - Maintains "latest-stable" symlink
    - Generates version navigation
    - Handles cleanup of SNAPSHOT versions upon release
- **Search Engine Optimization**:
    - Generates appropriate robots.txt
    - Maintains clean URLs structure
    - Proper indexing of stable versions

#### Usage

```yaml
- uses: eclipse-keypop/actions/doxygen@v1
  with:
    version: "1.0.0"              # Optional: Version to publish (auto-detected if not provided)
    repo-name: "keypop-example"   # Required: Repository name
```

#### Required Files

1. **Doxygen Configuration**:
    - Location: `.github/doxygen/Doxyfile`
    - Must use `%PROJECT_VERSION%` placeholder for version

2. **CMakeLists.txt Structure**:
```cmake
CMAKE_MINIMUM_REQUIRED(VERSION 3.5)

# Optional: Uncomment and modify when preparing a release candidate
#SET(RC_VERSION "2")

PROJECT(KeypopExample
        VERSION 2.1.1
        C CXX)

# Version handling
if(DEFINED RC_VERSION)
    SET(PACKAGE_VERSION "${PROJECT_VERSION}-rc${RC_VERSION}")
else()
    SET(PACKAGE_VERSION "${PROJECT_VERSION}")
endif()

# Package information
SET(PACKAGE_NAME "keypop-example")
SET(PACKAGE_STRING "${PACKAGE_NAME} ${PACKAGE_VERSION}")
```

The version is determined as follows:
- Base version is taken from the `PROJECT(VERSION X.Y.Z)`
- If `RC_VERSION` is defined, it becomes `X.Y.Z-rcN`
- If neither is present, it becomes `X.Y.Z-SNAPSHOT` for development builds

#### Documentation Structure

The action generates the following structure in your GitHub Pages:
```
repository-gh-pages/
├── 2.1.1-SNAPSHOT/      # Development version
├── 2.1.0-rc2/           # Release candidate
├── latest-stable/       # Symlink to latest stable version
├── 2.1.0/              # Stable version
├── list_versions.md    # Version listing
└── robots.txt         # Search engine directives
```

### Workflow Examples

#### Publishing Release Documentation

```yaml
name: Publish API documentation (release)
on:
  release:
    types: [published]

jobs:
  publish-doc-release:
    permissions:
      contents: write
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Extract repository information
        id: repo-info
        shell: bash
        run: |
          {
            echo "repo_name=${GITHUB_REPOSITORY#*/}"
            echo "version=${GITHUB_REF#refs/tags/}"
          } >> "$GITHUB_OUTPUT"

      - name: Generate and prepare documentation
        uses: eclipse-keypop/keypop-action-docs/doxygen@v1
        with:
          repo-name: ${{ steps.repo-info.outputs.repo_name }}
          version: ${{ steps.repo-info.outputs.version }}

      - name: Deploy to GitHub Pages
        uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./${{ github.event.repository.name }}
          enable_jekyll: true
          user_name: 'github-actions[bot]'
          user_email: 'github-actions[bot]@users.noreply.github.com'
          commit_message: 'docs: update ${{ steps.repo-info.outputs.version }} documentation'
```

This workflow is triggered when a release is published. It:
1. Checks out the repository with full history
2. Extracts the repository name and release version from the git tag
3. Generates the documentation using the specified version
4. Deploys the generated documentation to GitHub Pages

#### Publishing Documentation on Release

For release documentation, create a separate workflow triggered by release events. The workflow is similar but includes the version parameter:

```yaml
- uses: eclipse-keypop/actions/doxygen@v1
  with:
    version: ${{ steps.repo-info.outputs.version }}
    repo-name: ${{ steps.repo-info.outputs.repo_name }}
```

## Version Management

The action handles version management through the following rules:

1. **Version Detection**:
    - Reads base version from `PROJECT(VERSION X.Y.Z)` in CMakeLists.txt
    - Checks for `RC_VERSION` to determine if it's a release candidate
    - When neither is defined, treats as development (SNAPSHOT) version

2. **Version Types**:
    - Release (X.Y.Z): Final, stable versions
    - Release Candidate (X.Y.Z-rcN): Pre-release versions
    - SNAPSHOT (X.Y.Z-SNAPSHOT): Development versions

3. **Version Lifecycle**:
    - SNAPSHOT versions are replaced when their corresponding release is published
    - RC versions can exist alongside their base versions
    - Latest stable version is always accessible via the `latest-stable` symlink

## Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) before submitting a Pull Request.

## License

This project is licensed under the EPL 2.0 License - see the [LICENSE](LICENSE) file for details.
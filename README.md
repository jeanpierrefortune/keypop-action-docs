# Documentation Tools Action

Collection of GitHub Actions for generating and publishing documentation for Keypop libraries.

## Available Actions

### JavaDoc Documentation (`/javadoc`)

Action for generating and publishing Keypop libraries Java API documentation using JavaDoc.

```yaml
- uses: eclipse-keypop/documentation-tools-action/javadoc@v1
  with:
    version: "1.0.0"              # Optional: Version to publish (required for release)
    repo-name: "keypop-reader"    # Required: Repository name
```

### Doxygen Documentation (`/doxygen`)

Action for generating and publishing C++ API documentation using Doxygen.

```yaml
- uses: eclipse-keypop/documentation-tools-action/doxygen@v1
  with:
    version: "1.0.0"              # Optional: Version to publish (required for release)
    repo-name: "my-repo"          # Required: Repository name
```

## Usage Examples

### Publishing JavaDoc Documentation on Release

```yaml
name: Publish API documentation (release)
on:
  release:
    types: [published]
  workflow_dispatch:

jobs:
  publish-doc-release:
    permissions:
      contents: write
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - id: repo-info
        shell: bash
        run: |
          {
            echo "repo_name=${GITHUB_REPOSITORY#*/}"
            echo "version=${GITHUB_REF#refs/tags/}"
          } >> "$GITHUB_OUTPUT"

      - uses: eclipse-keypop/documentation-tools-action/javadoc@v1
        with:
          version: ${{ steps.repo-info.outputs.version }}
          repo-name: ${{ steps.repo-info.outputs.repo_name }}

      - uses: peaceiris/actions-gh-pages@v4
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./${{ github.event.repository.name }}
          enable_jekyll: true
          user_name: 'github-actions[bot]'
          user_email: 'github-actions[bot]@users.noreply.github.com'
          commit_message: 'docs: update ${{ steps.repo-info.outputs.version }} documentation'
```

### Publishing Doxygen Documentation on Release

```yaml
# Similar to JavaDoc example but using doxygen action
- uses: eclipse-keypop/documentation-tools-action/doxygen@v1
  with:
    version: ${{ steps.repo-info.outputs.version }}
    repo-name: ${{ steps.repo-info.outputs.repo_name }}
```

## Features

- Automatic version detection from source files
- Support for release and snapshot versions
- Generation of versioned documentation
- Creation of "latest-stable" links
- Version listing and navigation
- Support for release candidates (RC versions)

## Documentation Structure

The generated documentation follows this structure:
```
your-repo-gh-pages/
├── latest-stable/        # Symlink to latest stable version
├── 1.0.0/               # Stable version
├── 1.1.0-rc1/           # Release candidate
├── 1.1.0-SNAPSHOT/      # Development version
└── list_versions.md     # Version listing
```

## Requirements

### For JavaDoc Documentation
- Java project with proper package structure
- Version information in `pom.xml`

### For Doxygen Documentation
- Doxygen configuration file at `.github/doxygen/Doxyfile`
- Version information in `CMakeLists.txt`

## Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) before submitting a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
# Release Process for PR Merges into `master`

This document describes how to tie a version/release to each pull request merge into the `master` branch.

## 1. Choose a versioning strategy

- Use Semantic Versioning (SemVer): `MAJOR.MINOR.PATCH`.
- Keep the version in a single source of truth. In this repo, `.version` is a good candidate.
- Ensure `pyproject.toml` is consistent with the `.version` file.

## 2. Establish version bump rules for PRs

- `patch` for bug fixes and small improvements.
- `minor` for new features or non-breaking functionality.
- `major` for backwards-incompatible changes.

## 3. Require version bump in each PR

- Before merging any PR into `master`, update `.version` to the intended next version.
- If you prefer, use a PR template or checklist item to enforce this.
- Example PR checklist item:
  - [ ] Version updated in `.version`

## 4. Sync `pyproject.toml` with `.version`

- Keep the `version` field in `pyproject.toml` aligned with `.version`.
- Option A: update both files manually in the PR.
- Option B: add a simple script or CI check that validates `pyproject.toml` matches `.version`.

## 5. Automate release creation on merge to `master`

Create a GitHub Actions workflow that runs on push to `master` and does the following:

1. Read the value from `.version`.
2. Verify the repository is on `master`.
3. Create a Git tag using the version value, e.g. `v0.1.0`.
4. Create or draft a GitHub release for that tag.
5. Optionally publish artifacts or package builds.

### Example workflow triggers

```yaml
on:
  push:
    branches:
      - master
```

### Example release steps

```yaml
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Read version
        run: |
          VERSION=$(cat .version)
          echo "VERSION=$VERSION" >> $GITHUB_OUTPUT
      - name: Create tag
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git tag -a "v${{ steps.read-version.outputs.VERSION }}" -m "Release v${{ steps.read-version.outputs.VERSION }}"
          git push origin "v${{ steps.read-version.outputs.VERSION }}"
      - name: Create GitHub release
        uses: softprops/action-gh-release@v1
        with:
          tag_name: "v${{ steps.read-version.outputs.VERSION }}"
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

> Note: If the version tag already exists, you may want to fail the workflow or skip release creation.

## 6. Optional: Use PR labels or commits for release notes

- Use PR labels like `release/patch`, `release/minor`, `release/major`.
- Use a changelog generator or GitHub action to build release notes from PR titles and labels.
- This makes each release more descriptive.

## 7. Verify the final release

- After merge, confirm the GitHub release exists for the new version tag.
- Confirm `.version` and `pyproject.toml` are consistent in the merged commit.
- Optionally add a test in CI to verify the version file contents.

## 8. Suggested repository setup

- Keep `.version` at the repo root.
- Keep release automation in `.github/workflows/release.yml`.
- Add a PR template or contribution guide referencing this process.

## Summary

- Update `.version` for every PR that merges into `master`.
- Keep `pyproject.toml` and `.version` in sync.
- Use GitHub Actions to create tags and releases automatically on `master`.
- Use labels or release-note automation for better release transparency.

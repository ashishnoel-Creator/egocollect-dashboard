# Releasing a new version

This is the cheat-sheet for cutting a new release. Users on older versions will see a banner on launch and can one-click install.

## 1. Bump the version

Edit `ingest/version.py`:

```python
VERSION = "0.2.0"
```

Commit:

```bash
git add ingest/version.py
git commit -m "Bump to 0.2.0"
```

## 2. Build artifacts

On **macOS**:

```bash
python build.py
```

Produces `dist/EgoCollect.dmg` and `dist/EgoCollect.app`.

On **Windows** (separate machine):

```bash
python build.py
```

Produces `dist/EgoCollect-win.zip`.

## 3. Tag and publish

From the Mac where you built the DMG (or wherever you end up merging the artifacts — the Mac DMG must be built on Mac, the Windows zip on Windows):

```bash
git tag v0.2.0
git push origin main --tags

gh release create v0.2.0 \
  dist/EgoCollect.dmg \
  dist/EgoCollect-win.zip \
  --title "v0.2.0" \
  --notes "What changed in this release"
```

Users will see the update banner on their next app launch.

## 4. Verify

- Open the Release page: https://github.com/ashishnoel-Creator/egocollect-dashboard/releases/latest
- Confirm both `.dmg` and `.zip` are attached
- Confirm the `/releases/latest/download/EgoCollect.dmg` redirect works

## Notes

- **Asset filenames matter** — the in-app updater looks for `.dmg` and `.zip` assets by extension. Keep the names stable.
- **Version format** must be `vMAJOR.MINOR.PATCH` (e.g. `v0.2.0`). The updater uses this to compare against the app's bundled `VERSION`.
- To automate builds, add a GitHub Actions workflow that runs on tag push and uploads the artifacts. Skeleton at `.github/workflows/release.yml` (TODO).

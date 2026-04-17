# EgoCollect — Egocentric Data Collection Dashboard

Cross-platform desktop app for ingesting GoPro egocentric video from SD cards into organized folder structures on an external SSD. SHA-256 verified copies, per-SSD manifests, CSV reports, and in-app auto-updates.

## Download & install

Go to the folder for your platform:

- [**macOS**](mac/) → `EgoCollect.dmg`
- [**Windows**](windows/) → `EgoCollect-win.zip`

Or grab the latest build directly:

- [Latest Mac DMG](https://github.com/ashishnoel-Creator/egocollect-dashboard/releases/latest/download/EgoCollect.dmg)
- [Latest Windows ZIP](https://github.com/ashishnoel-Creator/egocollect-dashboard/releases/latest/download/EgoCollect-win.zip)

## How it works

1. Plug in an external SSD and click **Connect & lock SSD** — it stays the destination until it fills.
2. For each batch of cards (single camera or a 3-camera Left/Right/Head array), fill in the session details (date, employee, task) and click **Start copy**.
3. The app copies only `.MP4` files under each SD's `DCIM/` folder, verifies every file with SHA-256, writes a per-SSD manifest + CSV reports, then prompts to clear the source cards.
4. Multiple copy instances can run in parallel. SDs already in a running copy are hidden from the picker.

## Folder layout produced on the SSD

```
<SSD>/
  .egocentric-manifest.json
  <YYYY-MM-DD>/
    single-camera/<EmpID>/<Task>/session_NNN/
      *.MP4  +  checksums.sha256  +  session.json
    3-camera-array/<EmpID>/<Task>/session_NNN/
      Left/*.MP4, Right/*.MP4, Head/*.MP4  (each with checksums.sha256)
      session.json
  reports/
    <date>.csv, summary.csv
```

## In-app updates

On every launch the app checks this repo's GitHub Releases. When a newer version is published, a blue banner appears — click **Install update**:

- **Mac**: the new DMG is downloaded and opened in Finder; drag the new app into Applications.
- **Windows**: the new build downloads, replaces the current install, and restarts the app automatically.

## Developer setup

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

To build installers locally:

```bash
pip install -r requirements-dev.txt
python build.py
```

Produces `dist/EgoCollect.dmg` on Mac and `dist/EgoCollect-win.zip` on Windows.

See [RELEASING.md](RELEASING.md) for how to cut a new versioned release.

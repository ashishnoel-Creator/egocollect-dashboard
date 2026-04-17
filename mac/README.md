# Install on macOS

## 1. Download

[Download EgoCollect.dmg (latest)](https://github.com/ashishnoel-Creator/egocollect-dashboard/releases/latest/download/EgoCollect.dmg)

That link always points to the newest release — no version to remember.

## 2. Install

1. Double-click the downloaded `EgoCollect.dmg`.
2. A Finder window opens showing `EgoCollect.app`.
3. Drag `EgoCollect.app` into your **Applications** folder.
4. Eject the DMG (right-click the mounted disk → Eject).

## 3. First launch — IMPORTANT

The app isn't yet signed with an Apple Developer certificate, so macOS will refuse to open it normally the first time. One-time workaround:

1. Open **Applications** in Finder.
2. **Right-click** (or Control-click) on **EgoCollect** → choose **Open** from the context menu.
3. A warning dialog appears — click **Open** again.

After this one-time step, you can launch EgoCollect normally from Launchpad, Spotlight, or Applications.

## Updates

The app checks for new versions on GitHub every time it launches. When one is available, a blue banner appears at the top — click **Install update**:

1. The app downloads the new DMG in the background.
2. When finished, Finder opens the DMG automatically.
3. Drag the new `EgoCollect.app` into **Applications**, replacing the old one when prompted.
4. Relaunch the app.

You can also check manually via **Help → Check for updates…** in the menu bar.

## Uninstall

- Delete `EgoCollect.app` from your Applications folder.
- App data (session ledger, logs) lives in `~/Library/Application Support/EgoCollect/` — delete that folder to remove all traces.

## Troubleshooting

- **"EgoCollect can't be opened because Apple cannot check it for malicious software"** — follow the right-click → Open step above. This only needs to be done once.
- **App won't launch from Applications, but opens from the DMG** — you probably skipped step 2. Drag `EgoCollect.app` into Applications first.
- **Update banner keeps appearing after install** — make sure you dragged the new app to Applications *replacing* the old one. The app you launched may still be the old version from the DMG's mount point.

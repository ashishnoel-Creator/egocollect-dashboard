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

The app isn't yet signed with an Apple Developer certificate, so macOS Gatekeeper will block it the first time with a dialog that says **"Apple could not verify EgoCollect is free of malware…"** and only offers **Move to Trash** or **Done**.

Do this once:

1. In the blocking dialog, click **Done** to dismiss it.
2. Open **System Settings** → **Privacy & Security**.
3. Scroll down to the **Security** section.
4. You'll see a line like *"EgoCollect was blocked to protect your Mac."* — click **Open Anyway**.
5. Enter your Mac password when prompted.
6. A final dialog appears with an **Open** button — click it.

After this, launch normally from Launchpad, Spotlight, or Applications — no more prompts.

### Terminal alternative

If you'd rather not click through System Settings, open Terminal and paste:

```bash
xattr -cr /Applications/EgoCollect.app
```

Then launch EgoCollect normally. Same result — removes the Gatekeeper quarantine flag in one shot.

### Why this happens

On macOS 15 Sequoia and later, Apple removed the older right-click → **Open** shortcut for unsigned apps. The **System Settings → Privacy & Security → Open Anyway** path (or the Terminal one-liner) are the only working workarounds until the app is code-signed + notarized with an Apple Developer account.

## Updates

The app checks for new versions on GitHub every time it launches. When one is available, a blue banner appears at the top — click **Install update**:

1. The app downloads the new DMG in the background.
2. When finished, Finder opens the DMG automatically.
3. Drag the new `EgoCollect.app` into **Applications**, replacing the old one when prompted.
4. Relaunch the app. **You may need to repeat section 3 above** — the quarantine flag comes back with every fresh download, so Gatekeeper will block the new version once. Click through **System Settings → Privacy & Security → Open Anyway** again.

You can also check manually via **Help → Check for updates…** in the menu bar.

## Uninstall

- Delete `EgoCollect.app` from your Applications folder.
- App data (session ledger, logs) lives in `~/Library/Application Support/EgoCollect/` — delete that folder to remove all traces.

## Troubleshooting

- **"EgoCollect can't be opened" / "Apple could not verify…"** — follow section 3 above. System Settings → Privacy & Security → Open Anyway. This is expected on every fresh install and after every auto-update, until we add Apple code signing.
- **App won't launch from Applications, but opens from the DMG** — you probably skipped step 2 of install. Drag `EgoCollect.app` into Applications first, then follow section 3.
- **Update banner keeps appearing after install** — make sure you dragged the new app to Applications *replacing* the old one. The app you launched may still be the old version from the DMG's mount point.

# Install on Windows

## 1. Download

[Download EgoCollect-win.zip (latest)](https://github.com/ashishnoel-Creator/egocollect-dashboard/releases/latest/download/EgoCollect-win.zip)

That link always points to the newest release — no version to remember.

## 2. Install

1. Extract `EgoCollect-win.zip`. **Pick a user-writable location**, e.g.:
   - `C:\Users\<you>\Desktop\EgoCollect\`
   - `C:\Users\<you>\Documents\EgoCollect\`
   
   Avoid `C:\Program Files\` — the auto-update feature needs write access to the install folder and Program Files requires admin rights.
2. Open the extracted `EgoCollect` folder.
3. Double-click `EgoCollect.exe` to launch.

## 3. First launch

Windows SmartScreen may warn you because the app isn't yet code-signed.

1. Click **More info** in the warning dialog.
2. Click **Run anyway**.

After this one-time step, the app launches normally.

## Updates

The app checks for new versions on GitHub every time it launches. When one is available, a blue banner appears at the top — click **Install update**:

1. The app downloads the new build in the background.
2. When finished, EgoCollect closes, replaces itself with the new version, and restarts automatically.

You can also check manually via **Help → Check for updates…** in the menu bar.

## Uninstall

- Delete the `EgoCollect` folder.
- App data (session ledger, logs) lives in `%APPDATA%\EgoCollect\` — delete that folder to remove all traces.

## Troubleshooting

- **SmartScreen blocked the launch** — click **More info → Run anyway**. Only needed once.
- **Auto-update fails** — make sure the app is installed in a user-writable location (Desktop, Documents, `%LOCALAPPDATA%`). Program Files will not work without admin.
- **Antivirus flags the exe** — false positive, common with PyInstaller-packaged apps. Whitelist the folder or build from source.

# Session Keeper for Claude Code

> **Unofficial tool.** Not affiliated with or endorsed by Anthropic. "Claude" and "Claude Code" are trademarks of Anthropic.

A Windows tray app that shows your running **Claude Code** sessions (`claude` in a terminal) and **Claude Desktop** windows at a glance, snapshots them before a reboot, and brings them back after you sign in again.

Website: https://sessionkeeper.coldlapse.dev

## Features

- **See what's running**: working folder, session ID, title (first prompt), shell and terminal for each Claude Code session; position and state of each Claude Desktop window.
- **Snapshot → restart / shut down**: saves the current state and restarts. The next sign-in restores it automatically.
  - Claude Code sessions reopen in their own folders with `claude --resume <session ID>`, either as Windows Terminal tabs or as separate windows.
  - Claude Desktop is launched and its windows get their position, size and maximized state back.
- **Autosave**: every 5 minutes by default. What happens after an unexpected reboot (e.g. Windows Update) is up to you: ask whether to restore (default), restore without asking, or do nothing (keep autosaving only).
- **Selective restore**: pick only the sessions you want from any snapshot.
- **Exact session mapping (optional)**: install the Claude Code `SessionStart` hook and the app records which process belongs to which session ID, even with several sessions in the same folder.

The app's interface is currently **Korean only**.

## Install

| Method | Notes |
|---|---|
| Microsoft Store | (link after release) Automatic updates, starts at sign-in |
| Portable zip | From [Releases](../../releases): `ClaudeSessionKeeper-<version>-win64-portable.zip` → unzip → `ClaudeSessionKeeper.exe` |

Portable version:
- The exe is unsigned. If SmartScreen appears, choose **More info → Run anyway**.
- Keep `csk-hook.exe` and the `_internal` folder next to the exe.
- You can move the folder; paths are updated on the next launch.

Requirements: Windows 10 2004 or later, or Windows 11, x64.

## First-time setup

On the **Settings** tab:
1. **Install hook**: adds a SessionStart hook to `~/.claude/settings.json`. The original file is backed up as `settings.json.csk-bak`. The hook applies to sessions started or resumed after installing it.
2. **Start with Windows**: portable version only. The Store version starts at sign-in by default; turn it off under Startup apps in Task Manager.

## Uninstall

Press **Remove hook** on the Settings tab **before** uninstalling. Otherwise the hook stays in `~/.claude/settings.json`; if you already uninstalled, delete the `csk-hook.exe` entry under `hooks` → `SessionStart` yourself.

## Limitations

- Conversations **inside Claude Desktop windows** can't be read from outside, so they aren't restored. Only window placement and whether Desktop was running are restored.
- Terminal window positions are not restored.
- A reply being generated at the moment of the reboot is cut off. The conversation history stays on disk and can be resumed.
- For conversations that sat idle for a long time, Claude Code may ask "Resume this conversation?" when restoring. Pick **Resume** in each tab. Conversations used right up to the reboot usually don't ask.
- The Store version is launched by Windows together with other Store apps, one after another, so it can take 1–2 minutes after sign-in to start. The restore begins after the app starts plus the wait time (20 seconds by default).

## Privacy

No network access, no data collection. See the [privacy policy](https://sessionkeeper.coldlapse.dev/privacy.html).

## Development

```powershell
pip install -r requirements.txt pytest
python -m pytest -q tests           # unit tests
scripts\run_dev.bat                 # run from source
.\scripts\build.ps1 [-Msix]         # exe (portable zip) [+ MSIX]
```

## License

MIT © coldlapse

APP CONTROL CENTER - how to run BOL Images
Files are grouped by number: each number is one way to run the app. ON starts it, OFF stops/removes it.

00  Terminal      00 1 ON - Start in terminal.bat               Visible terminal, no reload (stops the background app first).
                  00 2 OFF - Stop in terminal.bat              Stops the server.
11  Background    11 1 ON - Start in background.bat             Starts the hidden tray app now.
                  11 2 OFF - Stop in background.bat             Stops the hidden tray app and server.
22  PC boot       22 1 ON - Install Auto-start at PC boot (no recovery).bat   Run once (Administrator). Server starts ~45s after the PC turns on,
                                                              before login, hidden, once. If it stops or crashes it is NOT restarted.
                                                              Removes the login auto-start (33). Task: BOLImages_Boot.
                  22 2 OFF - UnInstall Auto-start at PC boot (no recovery).bat      Removes the boot task. Does not stop a running server.
33  Login         33 1 ON - Auto-start at login (tray, recovery).bat   Run once. Starts hidden at every Windows login (tray icon, restarts on crash).
                  33 2 OFF - Remove login auto-start.bat        Removes the login auto-start.
44  Dev mode      44 1 ON - Dev mode (reload).bat               Edit code with --reload (stops background app, restores it afterwards).
                  44 2 OFF - Stop dev mode.bat                  Stops the server.

66  Full auto   66 1 ON - Boot task (recommended, Administrator). ONE task Tools-BOL_Images: starts at PC boot,
                  at every login, and every 5 minutes if the app is off (auto-recovery). Restarts the server if it crashes.
                  Never two copies: if the port is busy it does nothing.
                  00 1 ON (terminal) WINS: the task stands down while the terminal window is open and takes over
                  again within 5 minutes after you close it. 11 1 ON (tray) also replaces the task copy.
                  66 6 STOP pauses auto-start until next reboot or 66 4 RUN. 66 2 OFF removes the task.
Missing packages (e.g. "No module named 'fitz'") are reinstalled automatically into .venv by every ON file.

Helpers (not for double-click): _paused.ps1, boot_autostart.ps1, stop_background.ps1, background_tray.pyw (the tray app). Old file copies: _backups\
The original start_bol_images_app.bat / "stop app in backgroup.bat" in the project folder are unchanged.
HOST and PORT are read from settings.json (currently 127.0.0.1:8766), shared by all modes, so only one
mode runs at a time. After code edits the background app needs "Restart server" from its tray menu.
Tray icon: every mode shows it. 00/44 start it with --attach (status only, closes with the server); 22 (boot) adds a login
tray-only shortcut that attaches to the boot server (no Restart menu there: use 11 OFF then: schtasks /Run /TN BOLImages_Boot).
11 and 33 use the full tray (restart on crash, Restart server menu).
Server log: logs\server.log
Requires pystray and pillow (the login auto-start installs them if missing).

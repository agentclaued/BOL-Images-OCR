# Troubleshooting (field notes)

From a session on an office PC running the app from a network share (mapped to a temporary drive with `pushd`).

## `_venv.bat`: "cannot find the batch label specified - venv_ok"

This appeared on the first `call _venv.bat`; the second call worked. Labels are found by scanning the file, and LF-only line endings can make `goto :label` fail intermittently. The repo now sets `*.bat text eol=crlf` in `.gitattributes`. If the file is copied some other way, re-save it with CRLF endings. This is a likely cause, not a confirmed one.

## Auto-start task: "Access is denied" / "No password entered"

`window_autostart.ps1 -Mode Install` creates scheduled task `Tools-BOL_Images` and needs **Administrator**.

- Run it from an elevated window ("Run as administrator"), not a normal one.
- Use the full UNC path to the script from the admin window. A drive letter mapped by `pushd` is not visible there.
- "The user name or password is incorrect" means the account password was mistyped. Test with a throwaway task first:
  `schtasks /Create /TN BOL_TEST /TR "cmd /c echo hi" /SC ONSTART /RU "%COMPUTERNAME%\<user>" /RP * /RL HIGHEST /F`, then `schtasks /Delete /TN BOL_TEST /F`.
- Success looks like: `SUCCESS: The parameters of scheduled task Tools-BOL_Images have been changed`. The task starts the app about 45 s after boot, at each login, and every 5 minutes if the app is off.
- Do not paste admin-window output into the normal window. Each line runs as a command and gives harmless "not recognized" errors.

## `schtasks /Query`: "cannot find the file specified"

The task does not exist yet. Install it first.

## "Interrupted PDF could not be recovered because its source is unavailable"

At startup, a job was mid-run when the app stopped and its source file (upload or share path) is gone. This is informational. Delete the stuck job in the UI if it lingers.

## Port 8510 already in use

Another copy is running. Use `66 3 CHECK` for PIDs, or `66 6 STOP` / `00 2 OFF`. The server script deliberately refuses to start a second copy.

## Known good state from that session

A Python 3.13 venv imported fastapi, uvicorn, pymupdf and rapidocr, and Tesseract was detected. uvicorn served `/api/gallery`, `/api/process/status`, `/api/integrity/status` and `/api/spreadsheets` with 200 OK on port 8510.

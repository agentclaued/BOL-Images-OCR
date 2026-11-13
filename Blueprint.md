# Universal Project Blueprint

## 1. Purpose

Use this blueprint as the starting structure and operating standard for a new
local application. Adapt only the project-specific names, workflow rules, and
data formats. Keep source code, runtime data, documentation, deployment files,
and backups separate.

## 2. Recommended structure

```text
project-root/
|
|-- _backups/                    # Timestamped copies made before edits
|-- app/                         # Application source code
|   |-- __init__.py
|   |-- main.py                  # Startup, route registration, app creation
|   |-- config.py                # Settings and environment configuration
|   |-- models.py                # Shared models and schemas
|   |-- api/                     # Routes/controllers, split as the app grows
|   |   |-- __init__.py
|   |   |-- routes_items.py
|   |   |-- routes_jobs.py
|   |   `-- routes_admin.py
|   |-- services/                # Business logic
|   |   |-- __init__.py
|   |   |-- processing.py
|   |   |-- storage.py
|   |   |-- validation.py
|   |   |-- search.py
|   |   |-- integrations.py
|   |   `-- helpers.py
|   |-- static/                  # CSS, JavaScript, local images/icons
|   `-- templates/               # HTML templates, when applicable
|
|-- data/                        # Persistent runtime data, never source code
|   |-- database/
|   |-- uploads/
|   |-- outputs/
|   |-- logs/
|   |-- cache/
|   `-- temporary/
|
|-- tests/                       # Automated tests and safe test fixtures
|   |-- fixtures/
|   `-- test_*.py
|
|-- scripts/                     # Launch, backup, repair, and maintenance
|   |-- start_app.bat
|   |-- watch_app.ps1
|   `-- backup_data.ps1
|
|-- docs/                        # Project documentation
|   |-- ARCHITECTURE.md
|   |-- OPERATIONS.md
|   |-- DEPLOYMENT.md
|   `-- TROUBLESHOOTING.md
|
|-- deployment/                  # Clean package for another computer
|   |-- app/
|   |-- scripts/
|   |-- docs/
|   |-- requirements.txt
|   |-- .env.example
|   `-- README.md
|
|-- requirements.txt
|-- .env                         # Local secrets/settings; never commit
|-- .env.example                 # Safe settings template
|-- .gitignore
|-- README.md
`-- AGENTS.md                    # Project-specific instructions
```

## 3. Application backbone

```text
User interface or API
        |
        v
Routes/controllers
        |
        v
Services/business rules
        |
        v
Storage, background jobs, and approved integrations
        |
        v
Persistent runtime data in data/
```

### Responsibilities

| Area | Responsibility |
| --- | --- |
| `app/main.py` | Start the application and register routes. Keep it thin. |
| `app/api/` | Receive requests, validate input, call services, return responses. |
| `app/services/` | Hold business logic and workflows. |
| `app/config.py` | Read and validate configuration without hard-coded machine settings. |
| `data/` | Hold generated output and runtime state only. |
| `tests/` | Verify behavior using safe, non-production data. |
| `scripts/` | Make routine start, backup, repair, and maintenance actions repeatable. |
| `deployment/` | Hold the portable, clean application package. |

## 4. Mandatory backup policy

Before editing any existing important file, create a timestamped backup.

### Files that require a backup

- Source code, scripts, configuration, and documentation.
- Database files, user data, uploads, output files, and templates.
- Deployment-package files.
- Any file whose loss or accidental change would matter to the user.

### Backup rules

1. Create the backup before modifying the original.
2. Confirm that the backup exists before the edit.
3. Never overwrite a previous backup.
4. Use a timestamp in `YYYY-MM-DD-HHMMSS` format.
5. Preserve the original relative path inside the backup snapshot.
6. For a multi-file change, create one timestamped snapshot folder before the first edit.
7. Retain backups until the user explicitly authorizes their removal.
8. Do not back up disposable artifacts such as caches, virtual environments,
   compiled files, or temporary render output.

### Backup layout

```text
_backups/
`-- 2026-09-03-143025/
    |-- app/
    |   `-- main.py.bak
    |-- scripts/
    |   `-- start_app.bat.bak
    `-- requirements.txt.bak
```

## 5. Architecture rules

- Keep `main.py` focused on application startup and route registration.
- Keep route/controller files thin.
- Put business logic in `app/services/`.
- Keep file and database access separate from business rules.
- Use one module per clear responsibility.
- Prefer small, focused functions with descriptive names.
- Avoid circular imports and oversized all-purpose modules.
- Keep generated data out of source-code directories.
- Do not add unrelated frameworks, features, or dependencies.

## 6. Data safety and privacy

- Treat user data as important and potentially sensitive.
- Keep persistent runtime data under `data/`.
- Preserve original files whenever the workflow requires it.
- Never overwrite originals unless explicitly requested.
- Prefer reversible actions such as moving files to `Trash/` or an archive.
- Never permanently delete data without explicit user approval.
- Validate paths before reading, writing, moving, or deleting files.
- Do not log passwords, tokens, or sensitive user content.
- Do not send user data to an external service without explicit approval.

## 7. Configuration and secrets

- Do not hard-code credentials, tokens, passwords, ports, paths, or URLs.
- Read settings from environment variables or `app/config.py`.
- Keep real local values in `.env`.
- Never commit `.env`, private keys, user data, or production databases.
- Keep `.env.example` with safe placeholders.
- Validate required settings at application startup.

Example `.env.example`:

```env
APP_HOST=127.0.0.1
APP_PORT=8000
DATA_DIR=data
LOG_LEVEL=INFO
```

## 8. External dependencies and integrations

- Add a dependency only when it is necessary.
- Prefer maintained, stable libraries.
- Record required packages in `requirements.txt` or the package manifest.
- Document non-package system requirements in `docs/`.
- Do not silently install system software or change system settings.
- Use external APIs only with explicit authorization where user data may leave
  the computer.
- Fail safely and show clear messages when an integration is unavailable.

## 9. Background jobs

- Move long-running work outside the normal request-response path.
- Persist job state so interrupted work can resume safely.
- Record status, progress, timestamps, and meaningful error messages.
- Reuse completed work when resuming a job.
- Keep incomplete work in `data/temporary/` or a dedicated processing folder.
- Remove temporary work only after final output has been created and verified.

Suggested job states:

```text
queued -> running -> completed
                 -> held -> running
                 -> failed
                 -> cancelled
```

## 10. User interface standards

- Keep screens clear, task-focused, and understandable to non-technical users.
- Provide loading, success, error, and empty-state messages.
- Require confirmation for destructive actions.
- Make downloads download files rather than unexpectedly opening them.
- Do not show stack traces, secrets, internal paths, or raw system errors to users.
- Use readable labels, accessible controls, and sensible keyboard behavior.

## 11. Logging and error handling

- Log important operations, warnings, and failures with useful context.
- Keep detailed technical errors in logs and show friendly errors to users.
- Do not expose internal implementation details through the UI or API.
- Ensure a failure does not corrupt existing user data.
- Record enough information to safely diagnose and retry failed work.

## 12. Testing and verification

- Run relevant tests after each change.
- Add tests for new or changed business logic where practical.
- Test normal behavior and expected failure cases.
- Verify APIs with realistic requests.
- Verify file operations with safe test data.
- Verify UI changes in a browser when applicable.
- Do not report a change as complete without checking it.

Minimum test types:

```text
Unit tests:         Individual functions and service modules.
Integration tests:  Routes, storage, and workflow interactions.
Regression tests:   Previously fixed defects.
Manual checks:      UI behavior, file output, and application startup.
```

## 13. Documentation requirements

Update documentation whenever setup, behavior, commands, configuration,
recovery, or deployment changes.

Maintain:

```text
README.md              Overview, installation, and quick start.
docs/ARCHITECTURE.md   Structure, components, and data flow.
docs/OPERATIONS.md     Run, backup, restore, repair, and maintenance steps.
docs/DEPLOYMENT.md     Portable deployment instructions.
docs/TROUBLESHOOTING.md Common problems and resolutions.
```

## 14. Deployment package rules

Synchronize `deployment/` whenever relevant application files change.

Include:

```text
Application source code
Static files and templates
Dependency manifest
Configuration template
Start and maintenance scripts
Documentation
```

Exclude:

```text
User data
Uploads
Generated output
Databases
Logs
Cache and temporary files
Secrets and .env files
Virtual environments
Compiled/cache files
```

## 15. Git safety

- Inspect the working tree before edits.
- Preserve unrelated changes.
- Do not use destructive commands such as `git reset --hard` or force push
  without explicit approval.
- Do not commit secrets, runtime data, logs, caches, uploads, or databases.
- Keep commits focused and write outcome-based commit messages.
- Keep `.gitignore` current.

## 16. Completion checklist

Before marking work complete:

1. A timestamped backup was made before edits.
2. The requested change is implemented.
3. Unrelated code and data remain untouched.
4. Relevant tests or practical checks have passed.
5. Data safety and error handling are preserved.
6. Documentation was updated if behavior or operation changed.
7. The deployment package was refreshed if deployment-relevant files changed.
8. The final report lists changed files, backups, verification, and limitations.

## 17. Actions requiring explicit approval

Never perform these without direct user authorization:

- Permanent deletion of user data.
- Uploading, sharing, publishing, emailing, or externally transmitting data.
- Cloud processing of local user files or content.
- Installing system software or modifying machine-wide configuration.
- Replacing original user files.
- Resetting or overwriting unrelated version-control changes.
- Purchasing services, creating paid accounts, or changing subscriptions.

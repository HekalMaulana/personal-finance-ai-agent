# Optional Hermes cron (Lesson 6B)

Use a trusted checkout, a private Hermes profile, and an **existing fictional ledger**. The scheduler and runner need Python 3.12+ but no reporting packages, model credentials, or model calls. Do not put personal data in the ledger. The project does not install, configure, or start a gateway or operating-system service.

## Check compatibility and install paused

1. Run `hermes cron create --help`. The installer requires `--script`, `--no-agent`, `--interpreter`, `--timezone`, `--paused`, `--deliver`, `--failure-deliver`, `--catch-up`, and `--no-wrap-response`. It fails closed rather than using an LLM or assuming the profile's timezone. The job is created at `0 9 * * *` with `--timezone Asia/Pontianak`, so a UTC server still targets 02:00 UTC (09:00 WIB). Hermes must be able to resolve this IANA zone. If the flags or zone are unavailable, use the manual fallback below.
2. In your shell set `HERMES_HOME` to the absolute path of the **existing profile directory** used by your intended scheduler. Do not point it inside the clone. Use `export HERMES_HOME=/absolute/profile/path` in Bash or `$env:HERMES_HOME = 'C:\absolute\profile'` in PowerShell. If PATH resolves a wrapper that fails, set `FINANCE_HERMES_EXECUTABLE` in the same shell to the absolute path of the working Hermes executable (`.exe` on Windows); check the executable's own `cron create --help`.
3. Run from the checkout, replacing `lesson5d-demo` with your existing fictional ledger. Commands below use Bash. In PowerShell replace `./.venv/bin/python` with `.\.venv\Scripts\python.exe`.

```bash
./.venv/bin/python -B finance_cron.py dry-run --ledger lesson5d-demo
./.venv/bin/python -B finance_cron.py install --ledger lesson5d-demo --confirm
./.venv/bin/python -B finance_cron.py status
```

Dry-run checks the ledger without writing to it or to Hermes. Install copies a bound runner to `HERMES_HOME/scripts/` and creates one job **paused**. `status` describes the project job, not scheduler liveness. `hermes cron status` checks for a live ticker on the same profile. Verify the job settings and next run locally with `hermes cron list --all` (it may also show unrelated jobs; do not share that output). A running gateway/ticker is required for automatic execution. If it is missing, leave the job paused and use the fallback. Do not run `hermes cron tick` on a shared profile just to test this job: it can also run other due jobs.

## Activate explicitly and manage lifecycle

```bash
./.venv/bin/python -B finance_cron.py resume --confirm
./.venv/bin/python -B finance_cron.py pause
./.venv/bin/python -B finance_cron.py uninstall
```

Only `resume --confirm` activates a newly installed job. Success and failure delivery are local only; check local Hermes state/output under `HERMES_HOME/cron/` and use `finance_analysis.py history` for full results. The runner writes a short report to stdout only for new successful results; no due work or replay produces no stdout. Errors use generic stderr and a nonzero exit; after a partial failure, inspect SQLite for already committed results and retry failed periods explicitly through Lesson 6A. Hermes itself may keep local run diagnostics even on silent ticks.

The daily trigger is stable across installer reruns and gateway restarts because Hermes persists the job and SQLite persists period identities. Hermes catch-up is enabled; the analysis window still decides which periods can run. Before moving/updating the checkout, ledger binding, or venv, pause and allow any in-flight run to finish; recreate the venv at the new path, then rerun `install --ledger … --confirm` from the new checkout and `resume --confirm` when ready. An identical install preserves the job's current state. Stop on a name/script collision or unexpected drift; inspect the same profile before editing anything manually. Do not manage the same job concurrently from other Hermes interfaces. Before uninstalling, pause and let any in-flight analysis finish; uninstall does not cancel it. The installer records the exact Hermes job ID and refuses to adopt an unrecognized job. Uninstall removes only this job and its managed script, not the ledger, reports, or Hermes history. A small project-specific installer lock file remains in the profile.

## Tested fallback without Hermes or a gateway

```bash
./.venv/bin/python -B finance_cron.py dry-run --ledger lesson5d-demo
./.venv/bin/python -B finance_cron_runner.py --ledger lesson5d-demo run
```

Run manually after 09:00 WIB, including after restart. The same runner also works from an existing private OS scheduler; on an explicitly UTC scheduler the equivalent daily hour is 02:00. OS scheduler registration and automatic gateway ticks were not exercised in this milestone. Use local output only; Telegram remains planned.

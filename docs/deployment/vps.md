# VPS deployment overview

This is a proposed single-user setup. The Python workflow has been exercised on Ubuntu under WSL, not on a real VPS. A 2 GB VPS is a trial size, not a verified minimum. Start with a remote model provider rather than local inference; avoid optional browser and desktop components on a small server. Monitor RAM, swap, disk and OOM events during installation, representative chats and a workbook export before keeping the service on that size.

## Prepare the host

- Use Ubuntu 24.04 LTS, a dedicated non-root account, SSH access, and a private persistent filesystem. Follow the [Linux guide](linux.md) from that account. If the repository is private, use your own GitHub access; do not put credentials in the clone URL.
- Keep the checkout on persistent storage: its `data/` holds the ledgers and `reports/` holds the generated workbook. Use a private, persistent Hermes home for settings, auth, sessions and logs. Never point `HERMES_HOME` into the checkout. Check the mount is present before starting and use restricted permissions (`umask 077` before creating state directories).
- The example below assumes you cloned into `$HOME/personal-finance-ai-agent`; substitute your own path. Use the same `HERMES_HOME` at setup and at every launch. Enter credentials through `hermes setup model` using your own provider; if the provider uses a key, follow its environment variable instructions. No project `.env` is read by the Python CLI, and no Telegram credentials are needed.

## Start and restart

For initial testing over SSH, use an interactive `tmux` session (install tmux separately if needed). Run the following inside that session:

```bash
umask 077
export HERMES_HOME="$HOME/.hermes-finance"
export PATH="$HOME/.local/bin:$PATH"
cd "$HOME/personal-finance-ai-agent"
hermes setup model      # first launch only
hermes doctor
hermes skills trust     # after reviewing this checkout; repeat if trust is missing
hermes
```

Start tmux with `tmux new -s finance`. Detach with Ctrl+B then D, and reconnect after SSH logout with `tmux attach -t finance`. To restart Hermes, exit the conversation with `/exit` and relaunch `hermes` from the same directory and environment. tmux does not survive a reboot. No background application service is installed by this project.

If a later, validated deployment needs boot-time startup, evaluate the [Hermes gateway service](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/) under the same unprivileged account. Configure the service's environment and terminal working directory explicitly, and test start, restart, shutdown, and logs before enabling it at boot. Do not expose a dashboard or gateway port for this interactive SSH setup. Telegram remains planned.

## Update through Git

Stop Hermes and any other CLI writers, take a backup, then use `git status --short` and `git pull --ff-only` from the clean checkout. Review changed skills before restarting. Refresh the venv with `./.venv/bin/python -m pip install -r requirements-reporting.txt` if requirements changed. Run the offline tests, then restart with the same workspace and environment. Avoid `git clean -fdx`; it can delete ignored runtime state. Upgrade Hermes separately using its upstream instructions.

## Backup and recovery

1. Stop Hermes and all CLI writers. Copy `data/` as a unit (including any SQLite sidecars), `reports/` if needed, and the Hermes home separately. Store encrypted copies outside the VPS with access limited to the owner. Hermes backups may contain authentication state and session transcripts.
2. Restore into a separate checkout on the persistent filesystem first. Recreate `.venv` from the requirements; don't copy an old venv. Restore the ledger directory as a unit; don't combine sidecars from different backups or overlay them on a live database. Reports are optional and can be regenerated.
3. Before switching back, check the restored SQLite file with the project's Python on a read-only connection. From the restored checkout (replace `lesson5d-demo` with the restored fictional ledger name):

   ```bash
   ./.venv/bin/python - <<'PY'
   from contextlib import closing
   from pathlib import Path
   import sqlite3

   db = Path('data/finance-cli/lesson5d-demo.db').resolve()
   with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as conn:
       result = conn.execute('PRAGMA integrity_check').fetchall()
   if result != [('ok',)]:
       raise SystemExit(f'Integrity check failed: {result}')
   print('ok')
   PY
   printf '%s\n' '{}' | ./.venv/bin/python -B finance_cli.py --ledger lesson5d-demo summary
   ```

   Expect `ok` from the integrity check and compare the summary with known totals. Try an explicit export in the restore checkout. Restore Hermes state only under the intended account and permissions, or configure a new Hermes home and sign in again. Recheck project trust after a path change. Test recovery with synthetic data before relying on it.

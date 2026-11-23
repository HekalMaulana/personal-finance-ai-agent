# VPS deployment overview

This is a proposed single-user setup. The Python workflow has been exercised on Ubuntu under WSL, not on a real VPS. A 2 GB VPS is a trial size, not a verified minimum. Start with a remote model provider rather than local inference; avoid optional browser and desktop components on a small server. Monitor RAM, swap, disk and OOM events during installation, representative chats and a workbook export before keeping the service on that size.

## Prepare the host

- Use Ubuntu 24.04 LTS, a dedicated non-root account, SSH access, and a private persistent filesystem. Follow the [Linux guide](linux.md) from that account. If the repository is private, use your own GitHub access; do not put credentials in the clone URL.
- Keep the checkout on persistent storage: its `data/` holds the ledgers and `reports/` holds the generated workbook. Use a private, persistent Hermes home for settings, auth, sessions and logs. Never point `HERMES_HOME` into the checkout. Check the mount is present before starting and use restricted permissions (`umask 077` before creating state directories).
- The example below assumes you cloned into `$HOME/personal-finance-ai-agent`; substitute your own path. Use the same `HERMES_HOME` at setup and at every launch. Enter credentials through `hermes setup model` using your own provider; if the provider uses a key, follow its environment variable instructions. No project `.env` is read by the Python CLI, and no Telegram credentials are needed.

## Start and restart interactive chat (optional)

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

## Persistent scheduler (explicit VPS opt-in)

The interactive `hermes` session above is not the scheduler. Use the [Hermes-managed systemd user service](https://hermes-agent.nousresearch.com/docs/user-guide/messaging#as-a-service) on a Linux VPS. Use a dedicated non-root account and the same `HERMES_HOME` for every gateway, cron, and project command. Start with a dedicated, empty profile: no model setup, messaging adapters, or public port is needed for script-only cron. A foreground `hermes gateway run` can be used for VPS diagnosis instead of the service; stop it before starting the service. Do not use `--replace` to troubleshoot a different profile.

1. As the service user, set `umask 077`, `export HERMES_HOME="$HOME/.hermes-finance"`, and `mkdir -p "$HERMES_HOME"`. Set `PATH` for your existing Hermes launcher and check `hermes --version`, `hermes gateway install --help`, and `hermes cron create --help`. The host should have working IANA timezone data (`Asia/Pontianak`). Check UTC with `date -u`. Keep the host clock unchanged.
2. As the same user, follow [paused installation](cron.md#check-compatibility-and-install-paused). Leave the job paused until the ticker and the deployment checks pass. Use a private checkout on persistent storage. The interpreter must be the absolute `$CHECKOUT/.venv/bin/python` path as invoked, not its symlink target. The generated script is readable by that user (`0600`, no executable bit required); its new `scripts/` directory is `0700`. Ensure the service user can traverse the checkout/profile paths and read and write the ledger and its parent directory. The runner uses the bound checkout as its working directory; systemd's working directory need not be the finance checkout.
3. After reviewing the profile and opting into boot persistence on the VPS, enable lingering for the dedicated account (administrator authorization required), then use the Hermes service commands as the service user:

   ```bash
   sudo loginctl enable-linger "$(id -un)"
   hermes gateway install
   hermes gateway start
   hermes gateway status
   hermes cron status
   ```

   Use `hermes gateway restart` and `hermes gateway stop` under the same profile. Inspect the exact installed unit and its journal with `systemctl --user list-unit-files 'hermes-gateway*.service'` and `journalctl --user -u UNIT -n 50`, replacing `UNIT` with the unit for this profile. Check `systemctl --user is-enabled UNIT`, `systemctl --user show UNIT -p ActiveState -p User -p WorkingDirectory`, and inspect the unit locally (`systemctl --user cat UNIT`) to confirm the intended profile and launch path; don't share its environment or logs. If the unit/profile or ticker does not match, leave the job paused. `hermes cron status` may need a ticker interval before it shows a heartbeat.
4. Activate only after the pre-activation checks below and only on the intended VPS profile. `0 9 * * *` in `Asia/Pontianak` is 02:00 UTC. Recheck the next run and local delivery after `resume --confirm`. Use the manual runner if the service or safe cron flags are unavailable.

## Fresh-clone acceptance checklist

- [ ] Follow the [Linux guide](linux.md) for the fresh clone and venv. For scheduler-only verification no reporting dependency is needed. From the clone, seed an empty, fictional ledger only if `lesson5d-demo` is new: `./.venv/bin/python -B -c 'from finance_storage import TransactionStore; TransactionStore("data/finance-cli/lesson5d-demo.db")'`. Verify `dry-run`, paused `status`, and the same job ID after a repeat install. Run the [disposable cron smoke](cron.md#disposable-smoke-test) with the VPS Hermes executable before configuring a persistent job.
- [ ] Verify the managed gateway and ticker with the commands above. With the deployment job still paused, restart the gateway; verify the job ID and paused state survive, and verify a fresh heartbeat. Test timed dispatch and stop/start recovery in a disposable profile before relying on the service. Use a short synthetic schedule there only; never edit the deployment job to speed up testing.
- [ ] Before approval to activate, verify private paths, venv, `no_agent`, local success and failure delivery, and the restored SQLite data. After explicit activation, verify the next run is 02:00 UTC. After a real firing, inspect local cron status/output and `finance_analysis.py --ledger lesson5d-demo history`; a no-op may be silent. Check that completed periods are unique and transactions/reports are unchanged. Errors before the engine starts may have only a Hermes diagnostic; calculation failures also appear in SQLite and are not retried automatically.
- [ ] Measure RAM/swap and disk before startup, while idle, and during a due script using `free -h`, `df -h`, and `systemctl --user show UNIT -p MemoryCurrent -p MemoryPeak` (if available). Check `journalctl -k -b` for OOM events where permitted. Measure chat/export separately only if deploying those workloads. 2 GB is not a tested minimum.
- [ ] Practice [backup and restore](#backup-and-recovery) into a separate checkout. Reboot the VPS in a maintenance window after explicit approval; verify the correct service starts **without the service user logging in first** (e.g. inspect service activation time from a separate admin account), the ticker returns, and job ID/state and SQLite history survive. Validate a post-reboot firing without duplicate periods. First real Linux Hermes, systemd/logout/reboot, and VPS capacity validation remain pending.

## Update through Git

Stop Hermes and any other CLI writers, take a backup, then use `git status --short` and `git pull --ff-only` from the clean checkout. Review changed skills before restarting. Refresh the venv with `./.venv/bin/python -m pip install -r requirements-reporting.txt` if requirements changed. Run the offline tests, then restart with the same workspace and environment. Avoid `git clean -fdx`; it can delete ignored runtime state. Upgrade Hermes separately using its upstream instructions.

## Backup and recovery

1. Pause the finance job, allow any in-flight analysis to finish, stop the gateway, and stop all other CLI writers. Copy `data/` as a unit (including any SQLite sidecars), `reports/` if needed, and the Hermes home separately. Store encrypted copies outside the VPS with access limited to the owner. Hermes backups may contain authentication state and session transcripts.
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

   Expect `ok` from the integrity check and compare the summary and analysis history with the originals. Restore Hermes state only under the intended account and permissions. Keep the gateway stopped until the restored job is verified paused; a restored script may still point to the old checkout. Reinstall while paused to bind the new absolute checkout and venv, or register a fresh paused job in a new profile. Repeat dry-run and status before resuming explicitly. Test recovery with synthetic data before relying on it.

# Personal Finance AI Assistant

An Indonesian-language Hermes Agent prototype for tracking fictional transactions, explaining cash flow, and trying personal finance plans. The Python CLI works without an LLM or provider account. Use synthetic data only.

## Features

| Status | Scope |
| --- | --- |
| Implemented | Transactions, filters and summaries, versioned corrections, recovery after interrupted writes, monthly budgets, emergency funds, savings goals, on-demand Excel export, and a scheduled analysis engine with manual CLI startup and an opt-in Hermes cron installer. The analysis skill can work without saving data. |
| Tested | Deterministic Python, SQLite, and Excel tests on Windows and Ubuntu under WSL. See [evaluation](docs/evaluation.md) for separate evidence from earlier Hermes conversation tests. |
| Planned | Live Telegram acceptance, real VPS validation, reminders. |

## Technology Stack

Hermes Agent for conversation and tool use, Markdown with YAML frontmatter for skills, Python with its built-in `sqlite3` module for the ledger, openpyxl for `.xlsx` export, and `unittest` for tests.

## Architecture Overview

```text
Hermes → project skills → Python CLI → SQLite → Excel (explicit export only)
```

Skills define what to ask, when to confirm changes, and how to verify results. `finance_cli.py` accepts one UTF-8 JSON object on stdin for a named fictional ledger. `finance_reporting.py` reads SQLite and verifies the workbook before replacing the previous copy. Analysis-only requests do not need the CLI. See the [architecture notes](docs/architecture.md).

## Prerequisites

- Git: tested with 2.56.1 on Windows and 2.43.0 on Ubuntu; older versions were not verified.
- CPython **3.12 or later**, with `venv`, pip, and the bundled `sqlite3`. Verified baseline: Python 3.12.6 / SQLite 3.45.3 on Windows and Python 3.12.3 / SQLite 3.45.1 on Ubuntu. No separate SQLite installation is needed.
- `openpyxl==3.1.5` for Excel and the full test suite. pip resolves its `et-xmlfile` dependency. Excel itself is not required.
- For chat only: Hermes Agent with project-local skill discovery, and a tool-capable model from a provider you choose. Hermes v0.23.3 was checked on Windows; older releases were not verified. Hermes manages its own Python separately.

## Quick Start

```text
git clone https://github.com/HekalMaulana/personal-finance-ai-agent.git
cd personal-finance-ai-agent
```

Create the project venv using the steps below. Run the offline tests, then configure Hermes for chat or skip to the [CLI walkthrough](docs/usage.md).

## Installation on Windows

From the clone in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-reporting.txt
```

See the [Windows guide](docs/deployment/windows.md) for the native Hermes CLI, provider setup, and verification commands.

## Installation on Linux

From the clone on Ubuntu 24.04, after installing Python with venv support:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-reporting.txt
```

See the [Linux guide](docs/deployment/linux.md) for system packages and Hermes setup.

## Running Hermes Agent

1. Install the [Hermes CLI](https://hermes-agent.nousresearch.com/docs/getting-started/installation). Run `hermes setup model` and `hermes doctor`. Use your own provider and the local terminal backend on the host where the clone and `.venv` live.
2. From the Git root, review `AGENTS.md` and [`.hermes/skills/`](.hermes/skills/). Run `hermes skills trust` for this checkout and launch `hermes` from the same directory. You don't need to install global finance skills. See [Hermes project-local skills](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills#project-local-skills).
3. In a new conversation, ask Hermes to list the project skills and load `personal-finance-analysis`. If discovery is unavailable, ask it to read the relevant reviewed `SKILL.md` from this checkout. That fallback does not prove automatic discovery.
4. Create a private Hermes profile per installation: point `HERMES_HOME` at a dedicated directory outside the clone and do not reuse a shared, developer, desktop, or cloud-synced profile. The deployment guides ([Windows](docs/deployment/windows.md), [Linux](docs/deployment/linux.md), [VPS](docs/deployment/vps.md), [Telegram](docs/deployment/telegram.md)) show the exact per-OS commands and permission checks.

For an API-key provider, use its documented environment variable or the private Hermes environment file (`hermes config env-path` locates it). For OAuth, use Hermes's sign-in flow. The finance CLI requires no environment variables and does not load a project `.env`.

## Usage Examples

Use a new fictional ledger called `lesson5d-demo`. Try these in order. The agent normally replies in Indonesian. Use a separate clone if you don't want the export to replace an existing workbook.

| Task | Sample prompt |
| --- | --- |
| Record an expense | “Catat pengeluaran uji fiktif Rp25.000 untuk Makanan di ledger `lesson5d-demo`, 1 November 2026 pukul 12:00 UTC+07:00.” |
| Analyze without saving | “Simulasikan arus kas bulanan: pendapatan Rp8 juta dan pengeluaran Rp5 juta termasuk cicilan. Tampilkan rumus dan jangan simpan.” |
| Set a budget | “Tetapkan anggaran Makanan Rp1 juta untuk November 2026 di ledger fiktif `lesson5d-demo`. Berapa sisanya?” |
| Plan an emergency fund | “Di ledger fiktif `lesson5d-demo`, tetapkan kebutuhan esensial Rp5 juta per bulan dan target 3 bulan.” Then request a Rp6 million opening balance and ask for coverage. |
| Set a savings goal | “Buat target Laptop Rp10 juta di ledger fiktif `lesson5d-demo`.” Then request a Rp2 million opening balance and confirm the preview. |
| Export Excel | “Buat laporan Excel untuk ledger fiktif `lesson5d-demo`.” |

The first prompt creates the ledger. Keep that name for later operations, and review changes that require confirmation. The [CLI walkthrough](docs/usage.md) includes commands and expected output.

## Scheduled Analysis (Lesson 6A)

Run `finance_analysis.py` with the project interpreter from the clone. The commands below use Linux Bash; on Windows PowerShell replace `./.venv/bin/python` with `.\.venv\Scripts\python.exe`. Use an existing fictional ledger. No stdin JSON is needed; output is JSON.

```bash
./.venv/bin/python -B finance_analysis.py --ledger lesson5d-demo check-due
./.venv/bin/python -B finance_analysis.py --ledger lesson5d-demo run-due
./.venv/bin/python -B finance_analysis.py --ledger lesson5d-demo history --limit 10
./.venv/bin/python -B finance_analysis.py --ledger lesson5d-demo status weekly 2026-11-16
./.venv/bin/python -B finance_analysis.py --ledger lesson5d-demo run-due --resume weekly 2026-11-16
```

Replace the sample period with an ID returned by `run-due` or `history`: `weekly YYYY-MM-DD` (the week's starting Monday) or `quarterly YYYY-Qn`. `check-due` previews due work and does not write. On application startup, `run-due` checks the latest four due weeks and latest due quarter, oldest first. Older unrecorded periods are skipped. Use `--resume` only for an existing unfinished job; failed jobs require this explicit retry and are limited to three attempts total. Inspect each returned job's `status` (`pending`, `running`, `completed`, `failed`); the CLI's `ok` means the command returned successfully, not that every analysis completed.

- Mondays 09:00 Asia/Pontianak: prior calendar week, Monday 00:00 through the next Monday 00:00 exclusive. Weekly spending uses effective transactions and is compared with the effective monthly budget for each month the week touches. Cash flow is not bank balance.
- January 1, April 1, July 1, October 1 at 09:00 Asia/Pontianak: emergency fund balance, target, coverage, progress, and shortfall. Catch-up reports the allocation observed when the job actually ran, not a historical or bank balance.

`run-due` writes only its SQLite journal. It never exports Excel or calls a model.

## Optional Hermes cron (Lesson 6B)

The [cron deployment guide](docs/deployment/cron.md) covers dry-run, installation, activation, pause, removal, and the manual fallback. `finance_cron.py` installs one paused job per Hermes profile. After explicit activation, the job invokes `finance_cron_runner.py` daily at 09:00 Asia/Pontianak (02:00 UTC), with `--no-agent` and local delivery only. No gateway or service is installed or started by this project. The runner can also be used directly without Hermes.

## Data Storage & Privacy

- Named ledgers go in `data/finance-cli/<name>.db` relative to the clone, not the shell's working directory. The separate library default (`data/finance.db`) is not used by the agent or tutorial.
- An explicit export replaces `reports/laporan-keuangan.xlsx`, even when you switch ledgers. Edits in Excel are not imported.
- Do not upload databases, SQLite sidecars, workbooks, logs, backups, `.env` files, or credentials. `.gitignore` is not a substitute for checking the proposed commit. See [backup and recovery](docs/deployment/vps.md#backup-and-recovery).
- SQLite is local, but chat prompts and tool results may reach your model provider and appear in local Hermes session logs. Use fictional data only.

## VPS Deployment Overview

VPS deployment is documented as a proposal and remains **unverified**: no step has been run on a real VPS. Service startup after reboot and 2 GB RAM capacity have not been validated. The [VPS guide](docs/deployment/vps.md) covers the fresh-clone checklist, optional Hermes-managed systemd gateway, and SQLite recovery.

## Telegram Integration

**Disabled.** Telegram financial access is disabled and must stay disabled until live transport and deployed-agent isolation are verified. The setup documented below is offline-verified on fictional data only. The [Telegram deployment guide](docs/deployment/telegram.md) uses Hermes's built-in gateway with a dedicated profile and owner-only DMs. The baseline can discover project skills and discuss fictional scenarios; the Telegram toolset does not include the terminal needed to invoke the finance CLI. Use the local CLI for ledger operations. The disposable smoke test needs no bot token, network, model call, gateway process, or persistent service. Live Telegram delivery and production isolation are not verified.

**Lesson 7B — bound confirmation, offline only.** `finance_telegram.py` validates and previews fictional income or expenses, then binds confirmation to the same owner/private chat, operation ID and preview digest. The SQLite journal expires pending actions after five minutes and commits the ledger entry and audit state together. Test it with `-p test_telegram_actions.py` added to the commands below. [See the offline example and security audit](docs/deployment/telegram.md#lesson-7b-offline-bound-confirmation). Hermes has sender metadata inside the gateway, but the skill-to-shell path is not an authorization boundary. Telegram ledger reads, writes, corrections, and Excel delivery remain disabled.

**Lesson 7C — offline gateway bridge and ledger isolation.** The official Hermes `pre_gateway_dispatch` hook can consume original owner DM commands before the model sees them. The Linux fixture service authenticates the gateway UID over a Unix socket and owns the SQLite file; neither the gateway nor the separate agent UID can open it. [Run the after-clone checks and review the remaining blockers](docs/deployment/telegram.md#lesson-7c-offline-trusted-bridge-and-ledger-isolation). Nothing is installed or enabled automatically: live Telegram ledger access (including status), corrections, exports, and delivery remain disabled.

**Lesson 7D — offline E2E readiness.** The installed Hermes Telegram adapter and trusted hook handle simulated owner commands and send exact previews/results to a recording bot transport. The Ubuntu WSL fixture exercises the hook-to-ledger path across Linux UIDs with one fictional Rp25,000 commit. See the [preflight and phased acceptance guide](docs/deployment/telegram.md#lesson-7d-offline-e2e-readiness). No bot token or model is needed for these checks. The bridge is not auto-loaded; live Bot API and effective deployed-agent isolation remain pending. Keep Telegram ledger reads and writes disabled.

**Lesson 8A — finance-only scope, offline verified.** An alternative owner-DM adapter recognizes complete finance commands and runs four fictional calculations without dispatching a model or tools. It refuses unrelated or mixed instructions and directs ledger or Excel requests to the local CLI. It is not installed or enabled by the stock gateway. See the [v0.23.4 source smoke and remaining blockers](docs/deployment/telegram.md#lesson-8a-finance-only-scope).

## Testing

From the clone with the reporting dependency installed:

- Windows PowerShell: `.\.venv\Scripts\python.exe -B -m unittest discover -s tests -q`
- Linux: `./.venv/bin/python -B -m unittest discover -s tests -q`
- Targeted CLI-to-Excel smoke test: append `-p test_reporting.py -k test_cli_only_exports_on_explicit_operation` to either command.

The tests create isolated fictional fixtures and need no credentials, network access, personal database, or Hermes session.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `hermes` not found | Open a new shell and check PATH against the official installer guide. |
| `openpyxl` missing or `dependency_missing` | Install `requirements-reporting.txt` using the project venv interpreter, not Hermes's managed Python. |
| Skills missing | Start from the Git root, review and trust the checkout, and start a new session. Check project discovery and the skills toolset. |
| `database_not_found` | Explicitly record a fictional transaction first and reuse that ledger name. |
| Export fails with Excel open | Close the workbook and retry. |
| Provider or model error | Run `hermes setup model` and `hermes doctor`. Never paste keys or private diagnostic logs into an issue. |

## Project Structure

```text
.hermes/skills/             Six project-local skills
finance_cli.py              Structured input and ledger dispatch
finance_storage.py          SQLite transaction storage
finance_budgets.py          Monthly budgets
finance_emergency.py        Emergency fund allocations
finance_savings.py          Savings goals
finance_reporting.py        Verified Excel export
finance_analysis.py         Scheduled analysis and SQLite run journal
requirements-reporting.txt  Reporting dependency
tests/                      Deterministic regression tests
docs/                       Architecture, usage, evaluation, and deployment
```

## Roadmap

1. Verify a fresh Linux Hermes install and run a focused conversational check.
2. Measure memory and disk use on a real VPS and test restart and recovery.
3. Test Telegram access controls, write confirmations, and report handling with fictional data before enabling reminders or scheduled triggers.

## Security Disclaimer

This prototype is not financial advice or production software. It does not connect to banks, move funds, or place trades. Hermes's local backend has your OS user's permissions; project instructions and repo trust are not a sandbox. Keep approvals enabled and review tool calls.

## Contributing

Use fictional fixtures, add focused tests for behavior changes, and run the full suite. For bug reports, include OS, Python and Hermes versions and a sanitized reproduction. See the [project rules](AGENTS.md) and [development log](docs/development-log.md). The maintainer's push rules do not transfer to other clones.

## License

The original project code and documentation are available under the [MIT License](LICENSE). Keep the copyright and permission notices when redistributing copies or substantial portions.

Hermes Agent, Python, SQLite, and reporting dependencies are separate and retain their own terms. The project does not bundle them. If redistributing `openpyxl` or its `et-xmlfile` dependency, retain their upstream notices and license files, including `et-xmlfile`'s Python license notice for included standard-library code. The project's MIT license does not relicense third-party components.

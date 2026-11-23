# Personal Finance AI Assistant

An Indonesian-language Hermes Agent prototype for tracking fictional transactions, explaining cash flow, and trying personal finance plans. The Python CLI works without an LLM or provider account. Use synthetic data only.

## Features

| Status | Scope |
| --- | --- |
| Implemented | Transactions, filters and summaries, versioned corrections, recovery after interrupted writes, monthly budgets, emergency funds, savings goals, and on-demand Excel export. The analysis skill can work without saving data. |
| Tested | Deterministic Python, SQLite, and Excel tests on Windows and Ubuntu under WSL. See [evaluation](docs/evaluation.md) for separate evidence from earlier Hermes conversation tests. |
| Planned | Real VPS validation, Telegram integration, scheduled reviews, and reminders. |

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

## Data Storage & Privacy

- Named ledgers go in `data/finance-cli/<name>.db` relative to the clone, not the shell's working directory. The separate library default (`data/finance.db`) is not used by the agent or tutorial.
- An explicit export replaces `reports/laporan-keuangan.xlsx`, even when you switch ledgers. Edits in Excel are not imported.
- Do not upload databases, SQLite sidecars, workbooks, logs, backups, `.env` files, or credentials. `.gitignore` is not a substitute for checking the proposed commit. See [backup and recovery](docs/deployment/vps.md#backup-and-recovery).
- SQLite is local, but chat prompts and tool results may reach your model provider and appear in local Hermes session logs. Use fictional data only.

## VPS Deployment Overview

The [VPS guide](docs/deployment/vps.md) describes a single-user Linux setup with persistent storage and a detachable SSH session. It has not been verified on a real VPS. Treat 2 GB RAM as a trial configuration, not a verified requirement.

## Telegram Integration

**Planned.** This repository does not configure or test a Telegram finance bot. Upstream Hermes gateway support does not verify this project's workspace, confirmations, or file handling over Telegram.

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
requirements-reporting.txt  Reporting dependency
tests/                      Deterministic regression tests
docs/                       Architecture, usage, evaluation, and deployment
```

## Roadmap

1. Verify a fresh Linux Hermes install and run a focused conversational check.
2. Measure memory and disk use on a real VPS and test restart and recovery.
3. Test Telegram access controls, write confirmations, and report handling with fictional data before adding reminders or scheduled reviews.

## Security Disclaimer

This prototype is not financial advice or production software. It does not connect to banks, move funds, or place trades. Hermes's local backend has your OS user's permissions; project instructions and repo trust are not a sandbox. Keep approvals enabled and review tool calls.

## Contributing

Use fictional fixtures, add focused tests for behavior changes, and run the full suite. For bug reports, include OS, Python and Hermes versions and a sanitized reproduction. See the [project rules](AGENTS.md) and [development log](docs/development-log.md). The maintainer's push rules do not transfer to other clones.

## License

No project license has been approved and no `LICENSE` file is included. Public availability would not by itself grant redistribution or modification rights. MIT is a candidate for maintainer review, not a license grant.

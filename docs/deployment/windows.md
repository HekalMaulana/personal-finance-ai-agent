# Windows installation

Target: native Windows 11 and PowerShell. You do not need WSL for this setup. The platform and runtime versions tested for this project are listed in [evaluation](../evaluation.md#lesson-5d--open-source-readiness--cross-platform-deployment).

1. Install [Git for Windows](https://git-scm.com/download/win) and [CPython](https://www.python.org/downloads/windows/) 3.12 or later with the `py` launcher. Open PowerShell and verify `git --version` and `py -3.12 --version`. If you installed a later Python, replace `-3.12` with its version.
2. Clone and set up the project:

   ```powershell
   git clone https://github.com/HekalMaulana/personal-finance-ai-agent.git
   Set-Location personal-finance-ai-agent
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements-reporting.txt
   .\.venv\Scripts\python.exe -B -m unittest discover -s tests -q
   ```

   Calling the venv interpreter directly avoids PowerShell script activation and keeps project packages separate from Hermes. The tests use fictional fixtures and do not need an existing ledger.
3. Install the native Windows CLI using the [official Hermes installation guide](https://hermes-agent.nousresearch.com/docs/getting-started/installation#without-hermes-desktop), then reopen PowerShell. From the clone, run `hermes --version`, `hermes setup model`, and `hermes doctor`. Choose your own provider and tool-capable model; keep credentials out of the clone.
4. Review [running Hermes](../../README.md#running-hermes-agent) to trust the project and start a session. Use the local terminal backend on the same machine as the clone. The skills select `.venv\Scripts\python.exe` directly, even if Hermes itself uses a different Python.

If `py` or `hermes` is not found after installation, open a new PowerShell window and check the PATH entries documented by its installer. If an export fails with the workbook open in Excel, close the workbook before retrying.

## Optional scheduled analysis

See the [cron deployment guide](cron.md). Use the native Hermes `.exe`, an absolute `HERMES_HOME` for the intended profile, and `.\.venv\Scripts\python.exe`. If a wrapper fails, point `FINANCE_HERMES_EXECUTABLE` at a working Hermes `.exe`. Start with dry-run; if no ticker is available, use the documented direct runner. The Windows smoke test used a temporary, paused job and did not start a gateway.

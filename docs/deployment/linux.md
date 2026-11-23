# Linux installation

Target: Ubuntu 24.04 LTS. The CLI and Excel workflows were tested under Ubuntu 24.04 in WSL; see [evaluation](../evaluation.md#lesson-5d--open-source-readiness--cross-platform-deployment) for the test setup and what was not exercised.

1. Install Git, curl and Python with venv support. On Ubuntu, run the following or ask your administrator to install the packages:

   ```bash
   sudo apt update
   sudo apt install git curl python3 python3-venv
   python3 --version
   ```

   Use Python 3.12 or later. On another distribution, use its package manager and check the installed Python version before continuing.
2. Clone into a user-owned directory on the Linux filesystem. On WSL, prefer your Linux home over a Windows-mounted drive.

   ```bash
   git clone https://github.com/HekalMaulana/personal-finance-ai-agent.git
   cd personal-finance-ai-agent
   python3 -m venv .venv
   ./.venv/bin/python -m pip install -r requirements-reporting.txt
   ./.venv/bin/python -B -m unittest discover -s tests -q
   ```

   If venv creation reports that `ensurepip` is missing, install the matching Python venv package. Do not install packages into the system interpreter to work around it.
3. Install the Linux CLI using the [official Hermes installation guide](https://hermes-agent.nousresearch.com/docs/getting-started/installation#without-hermes-desktop). Open a fresh shell, return to the clone, then run `hermes --version`, `hermes setup model`, and `hermes doctor`. Choose your own provider and tool-capable model. If Hermes is not on PATH, check the launcher path in the installation guide.
4. Follow [running Hermes](../../README.md#running-hermes-agent) to review the skills, trust the checkout, and chat. Use the local terminal backend with the repository on the same host. The skills call `./.venv/bin/python`; no activation is required.

## Optional scheduled analysis

Follow the [cron deployment guide](cron.md) and [VPS acceptance checklist](vps.md#fresh-clone-acceptance-checklist) after cloning. For scheduler-only use, create the venv but skip reporting dependencies, model setup, and full test discovery. Run `./.venv/bin/python -B -m unittest discover -s tests -p test_finance_cron.py -q`, then repeat with `-p test_scheduled_analysis.py`. Ubuntu WSL checks exercised the bound runner, private file modes, and venv path, not native Linux Hermes. The pinned `Asia/Pontianak` schedule maps to 02:00 UTC. If the gateway or required flags are unavailable, use the manual fallback.

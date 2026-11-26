# Telegram gateway — Lessons 7A–8A

**Fictional data only.** This is an opt-in, single-owner DM setup using [Hermes's built-in Telegram adapter](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram), not a bot framework. The baseline supports skill discovery and simulations without ledger access. Do not run a production bot, install a persistent service, or configure cron delivery from this guide. No gateway launch is needed on a development machine.

## Compatibility and workspace

Audited against Hermes Agent **v0.23.3**, local revision `caafe5389ae5`, on Windows. See the upstream [gateway](https://hermes-agent.nousresearch.com/docs/user-guide/messaging) and [project-local skill](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills#project-local-skills) docs. The native adapter supports long polling (used here), webhooks and media; none of the network paths was exercised. The Windows runtime did not have the optional Telegram SDK installed. On an approved deployment host, check for Telegram support; if the SDK is missing on this release, Hermes can provision its Telegram extra (`hermes pm install --extra telegram`), subject to operator approval. Do not install it into the finance venv.

Setting an **absolute `terminal.cwd`** to the clone root is necessary even if the gateway is launched from there. Hermes bridges this setting into `TERMINAL_CWD`; the prompt builder uses the effective cwd to resolve project context, and skill discovery walks to the nearest Git root and uses its trusted `.hermes/skills/`. `AGENTS.override.md` can take precedence over `AGENTS.md`, and `.hermes.md` / `HERMES.md` can take precedence over both. Do not add these overrides in this checkout. Run `hermes skills trust` against the reviewed clone with the same `HERMES_HOME` used for deployment. Trust and an absolute path do not sandbox the agent. Do not use `MESSAGING_CWD` or `TERMINAL_CWD` in `.env`, copy skills globally, or reuse a desktop or developer profile. After moving the clone, set the new cwd, trust it again and start a fresh session.

## 1. Prepare separate account, clone, and profile

Use one dedicated unprivileged OS account or VM per deployment. Use a fresh, private clone, with its own `data/finance-cli/`, `reports/`, and venv (see [Windows](windows.md) or [Linux](linux.md)). Keep the gateway checkout **free of ledgers, reports, backups, and real data**; use a separate local clone for ledger work. Never symlink or mount shared finance state. Give each deployment a different Telegram bot token, provider credentials, and a dedicated `HERMES_HOME` outside the checkout. Do not copy another profile's auth, sessions, or pairing store. Use a clean login environment with no inherited bot/provider credentials, allowlists, service overrides, or other adapters. A named profile under the same OS account alone does not isolate files or credentials.

**Windows PowerShell** — run under the dedicated standard account, not as administrator. Substitute the path of the fresh clone:

```powershell
Set-Location 'C:\path\to\personal-finance-ai-agent'
$clone = (Get-Location).Path
$env:HERMES_HOME = Join-Path $env:USERPROFILE '.hermes-finance-telegram'
New-Item -ItemType Directory -Path $env:HERMES_HOME -Force | Out-Null
icacls $env:HERMES_HOME
```

Verify the profile, clone and eventual `.env` ACLs; restrict access to the deployment account and necessary OS administrators/system. Do not put state under a shared or cloud-synced folder.

**Ubuntu / Linux VPS (Bash)** — run under the dedicated non-root account. Substitute your clone path:

```bash
umask 077
cd "$HOME/personal-finance-ai-agent"
clone="$PWD"
export HERMES_HOME="$HOME/.hermes-finance-telegram"
mkdir -p "$HERMES_HOME"
chmod 700 "$HERMES_HOME"
```

**Both shells**, with the same environment set each time. First verify `hermes config env-path` points inside the intended `HERMES_HOME`. Stop if it does not.

```text
hermes --version
hermes gateway run --help
hermes config env-path
hermes config set terminal.backend local
hermes config set terminal.cwd "$clone"
hermes config set gateway.multiplex_profiles false
hermes config set unauthorized_dm_behavior ignore
hermes config set --force platform_toolsets.telegram '[skills]'
hermes config set skills.inline_shell false
hermes config set skills.write_approval true
hermes config set --force platforms.telegram.extra.allow_admin_from '[0]'
hermes config set --force platforms.telegram.extra.drop_pending_on_cold_boot true
hermes config set approvals.mode manual
hermes skills trust "$clone"
```

Verify the saved deployment value with `hermes config get platform_toolsets.telegram`. The offline smoke checks this recipe in a temporary profile, not the effective deployment profile. `--force` here only permits the key in the config CLI, not overriding a running gateway. The `allow_admin_from` value `[0]` activates slash gating without granting admin to a real Telegram user: the owner retains `/help` and `/whoami`, not administrative commands. Do not grant `/sethome`, `/approve`, or `/skills` administration. Keep cron empty, other adapters and custom plugins/MCP unconfigured, and do not enable YOLO. Use `hermes setup model` with dedicated provider credentials only when preparing an approved live test.

## 2. BotFather and owner-only DM

1. For a separately approved live test, create a dedicated **test** bot using the official [@BotFather](https://t.me/BotFather) `/newbot` (username ends in `bot`). In BotFather disable **Allow Groups** (`/setjoingroups`), leave privacy mode on, and keep guest mode off. Never add the bot to a group/channel, give it channel admin privileges, or share it with other users. Use a fresh bot with no existing memberships.
2. Obtain the owner's positive numeric Telegram **user ID**, not a username, phone number, bot ID or group ID. The upstream guide describes [ID lookup](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram); if you use an ID lookup bot, send no secrets or financial data to it. Verify the ID is yours. Telegram's private bot chat ID equals the user's ID.
3. In a private local editor, save the following keys in the deployment profile's `.env` (UTF-8 without BOM). Replace every placeholder; configure exactly one digits-only owner ID in both ID fields. On Linux restrict `.env` to `0600` (`chmod 600 "$HERMES_HOME/.env"`); on Windows check its ACL before saving the token. Never put a token in command arguments, a clone `.env`, Git, screenshots, logs shared with others, or prompts/chat. Do not use auto-setup that restarts the gateway.

```dotenv
TELEGRAM_BOT_TOKEN=<token-issued-by-BotFather>
TELEGRAM_ALLOWED_USERS=<owner-numeric-user-id>
TELEGRAM_ALLOWED_CHATS=<same-owner-numeric-user-id>
```

`TELEGRAM_ALLOWED_USERS` filters senders. In this version that grant is **platform-wide**, not DM-only. `TELEGRAM_ALLOWED_CHATS` is a separate adapter gate for group/supergroup/channel messages; a positive DM ID excludes negative group/channel IDs. An empty chat list is **not** a group-deny setting. Do not set `TELEGRAM_GUEST_MODE`, group allowlists, free-response/observation settings, pairing grants, `TELEGRAM_ALLOW_BOTS`, `GATEWAY_ALLOWED_USERS`, `TELEGRAM_ALLOW_ALL_USERS`, `GATEWAY_ALLOW_ALL_USERS`, or `*` in any allowlist. Unknown DMs must be ignored (no pairing); without an owner allowlist the runner must deny. Leave `TELEGRAM_HOME_CHANNEL` and `TELEGRAM_WEBHOOK_URL` unset. Long polling needs outbound HTTPS, not inbound public ports.

## 3. Money, tools, and deployment blockers

Telegram authentication is not transaction authorization. This baseline does not read or write SQLite or export reports from chat, even after a DM says “confirm”. Use the local CLI and the relevant skill's checks in the separate ledger clone. For a write requested via an authorized local conversation, preview the exact ledger, operation and values (old → new where applicable), expected revision/version and reason when required; wait for a separate explicit reply confirming that preview. Do so **before** the first write (`prepare-add` itself can write). Use the structured CLI, keep the exact payload/idempotency key, and supply `confirmed` only where required and after actual confirmation. Ambiguous or stale approval does not carry over. After interruption, read status/history before retry; do not claim success until persisted results match.

Do not add terminal, file, code execution, delegation, browser, messaging, cron, or MCP toolsets to the Telegram profile. The `skills` toolset includes `skill_manage`; changes require staging with `skills.write_approval`, and the DM owner cannot approve them through slash commands. Leave staged mutations unapplied; do not enable inline shell. Tool choices, slash gating and prompt rules are not OS containment: other gateway features (e.g. attachment handling or `@` references), installed plugins, account compromise, and provider/session logs can expose data. A local shell, if enabled, runs with the gateway account's permissions and could read credentials or bypass CLI confirmation by writing SQLite directly. Shell approvals are not transaction approvals. Keep the data out of reach and never share finance data with a group or public channel.

**Blocker for real use:** Lesson 7B verifies bound authorization offline, not the trusted bridge from a live update or end-to-end data isolation. Do not enable Telegram ledger reads/writes, report delivery, or production use.

### Lesson 7B: offline bound confirmation

**Sender provenance audit (Hermes v0.23.3, `caafe5389ae5`).** In `plugins/platforms/telegram/adapter.py`, `_source_from_message_for_auth` takes identity from `Message.from_user` and `Message.chat`; `_build_message_event` creates a `SessionSource` and keeps `raw_message`. Some source fields have fallbacks, so a future finance adapter must require the actual private inbound message with a present, non-bot sender, rather than trust a routed chat ID. `gateway/authz_mixin.py::_is_user_authorized` gates gateway access. `gateway/run.py::_set_session_env` binds session context variables; `gateway/session_context.py` distinguishes per-turn `ACTOR_ID` from route `USER_ID` and its public `get_session_env` can fall back to process environment. `tools/environments/local.py::_inject_session_context_env` can copy the bound metadata to a local child environment. Thus Hermes has trusted metadata **inside** the gateway, but the model-driven skill → terminal → Python CLI path cannot prove identity or original approval: the model supplies tool args and a general shell can set its subprocess environment. A skills-only profile doesn't expose that CLI, and adding terminal would grant more than a finance operation allowlist.

**Offline operation contract.** The trusted harness selects an existing disposable fictional ledger, supplies an allowlist (empty by default), and passes the authenticated sender, same private chat, and original message separately from the request. `TelegramSource` is a data type, not a credential. No gateway handler, plugin, or CLI flag enables this API. Only `transaction.add` is allowed, for both income and expense, using the existing transaction validator and writer. `prepare` journals immutable normalized parameters and returns a preview, random UUID, digest and five-minute expiry without a ledger entry. The digest binds the preview to the operation, owner, chat, and expiry; it is not a secret or proof of identity. `confirm` compares exact original text and executes only the stored payload. `cancel` also requires exact original text. `status` uses a read-only SQLite connection. One SQLite transaction commits the journal state and ledger entry together; confirm replay is rejected, and after an uncertain response use `status`, not a fresh prepare. The journal records prepared parameters and the terminal transition (with transaction ID for commits); expiry uses a monotonic clock in the preparing process (the wall-clock deadline is informational). After a process restart, pending previews appear as expired and must be prepared again; committed and canceled outcomes remain available. Production handling of host suspension is not verified. This is not a tamper-proof security log.

**Example (test harness only, not live bot commands):** `prepare` with `{"operation_type":"transaction.add","parameters":{"transaction_type":"expense","amount_rupiah":15000,"category":"Makanan","occurred_at":"2026-01-01T12:00:00+07:00"}}` returns `operation_id` and `preview_digest` alongside the exact parameters. Pass those two fields to `confirm` only when the same owner's original message is exactly `confirm <operation_id> <preview_digest>`. For `cancel`, send only `operation_id` and simulate the exact original message `cancel <operation_id>`. `status` needs only `operation_id` plus trusted source. Run `python -B -m unittest discover -s tests -p test_telegram_actions.py -v` with the project interpreter. This needs no token, SDK, model or Excel export.

**Before enabling anything:** an independently trusted, narrow handler would need to show the exact preview directly (not an LLM paraphrase), parse confirmation from a fresh original non-forwarded/non-edited inbound owner message, and enforce update provenance and deduplication. Its ledger and writer must be isolated by OS permissions from agent tools and arbitrary code; verify both permissions and effective gateway features end to end. Until then, even status/ledger reads are not exposed to Telegram. Budgets, emergency funds, savings goals, and versioned transaction corrections/history remain on their existing local CLI paths only; no Telegram Excel export or scheduled delivery.

### Lesson 7C: offline trusted bridge and ledger isolation

**Extension point.** The installed v0.23.3 exposes `ctx.register_hook('pre_gateway_dispatch', callback)` with the original `MessageEvent` and gateway instance (`gateway/run_inbound_hooks.py`). Unlike `post_gateway_admission`, it carries `raw_message`, update ID, and edit metadata. Unlike `register_command`, it doesn't reduce the input to command args and a `SessionSource`. Adapter command intake checks sender authorization before dispatch; the runner invokes this hook *before* its own authorization, so the bridge independently denies by default. Webhooks, slash commands from local sessions, synthetic turns and shell/session environment are not credentials.

**Data flow.** `FinanceIngress` compares the raw Telegram sender, private chat, and message ID against the routed event and the single operator-selected owner. It rejects bots, absent/mismatched metadata, edits, forwards, replies, topics and mismatched raw/routed text. In the offline harness it consumes `/finance` before model dispatch and sends the exact JSON preview directly through a trusted reply callback. The narrow service accepts `prepare` (only `transaction.add`, with JSON parameters), `confirm <operation_id> <preview_digest>`, `cancel <operation_id>`, and `status <operation_id>`; nothing accepts a caller-selected database, arbitrary SQL, or agent-supplied authorization. Lesson 7B binds confirmation to the immutable preview, owner and chat. Fresh inbound messages have a five-minute age limit; the persistent `(chat, message)` receipt rejects redelivery across process restarts. Receipt creation (including for `status`) writes only receipt metadata. If a crash occurs between recording receipt and applying an action, the message is intentionally not retried: send a new status request. After service restart, pending previews expire; committed results remain queryable. The receipt journal is fixture-only, without pruning, and must not be reused across bot rotations or restored independently of the ledger.

**OS boundary.** The Linux fixture runs the Python service, trusted gateway client and untrusted agent under three different unprivileged UIDs. Only the service owns the `0700` ledger directory and `0600` database/sidecars; use a native Linux filesystem, not `/mnt/c`. The Unix socket sits in a service-owned setgid `2750` directory with a gateway-only group, mode `0660`, and both peers check Linux `SO_PEERCRED`. The agent must not share the gateway UID, even when it cannot open SQLite: that UID can submit privileged IPC. Keep all parent paths and executable code free of agent write access. No setuid launchers, sudo, privileged groups, shared descriptors, equivalent Windows access, or local backend under the trusted gateway identity are allowed.

**Tool audit.** Local terminal/background jobs and the Python execution kernel can open files or use SQLite under their process identity. File read/search/write/patch tools can read SQLite or alter state directly, and skill inline shell can spawn commands. The finance CLI, reporting, analysis and cron wrappers all depend on ordinary SQLite/file access; none supplies OS confinement. In-process plugins, delegation, custom MCP, browser/desktop tools, attachments, file references, and any agent-accessible backups or exports must also be excluded from the trusted data path. Profiles, toolset filters, command approvals and `AGENTS.md` are defense in depth only. A process sharing the trusted UID or direct access to the gateway process invalidates the bridge.

**After clone (offline only).** Run `python -B -m unittest discover -s tests -p 'test_telegram*.py' -q` with the project interpreter, then run the installed-Hermes smoke below. From the project root on Ubuntu/Linux, an administrator can run `sudo python3 -IB tests/smoke_telegram_isolation.py` with a trusted checkout and a native temporary directory. From Windows with Ubuntu WSL installed, the equivalent is `wsl.exe -d Ubuntu -u root -- python3 -IB /mnt/c/path/to/personal-finance-ai-agent/tests/smoke_telegram_isolation.py` (adjust the clone path). This probe uses existing Ubuntu test UIDs and deletes the fixture; it installs no users, services, or plugins. Only the test administrator starts it as root; the three subprocess identities are unprivileged.

**Lesson 7C boundary.** Its two probes did not compose adapter intake, hook, and reply or verify deployed-agent isolation. Lesson 7D extends the offline probes below; a live plugin or service is still not installed and all Telegram ledger access remains disabled.

### Lesson 7D: offline E2E readiness

**Default: no ledger access.** `finance_telegram_gateway.py` is an opt-in registration helper, not an installed plugin, agent tool, or service. The trusted hook validates the original raw private DM and routed sender/chat, then checks gateway authorization, running state, drain and Hermes emergency stop before dispatch. It replies only to the validated owner's numeric chat, using the connected Hermes Telegram adapter's Bot API client with plain JSON and link previews off. No delivery via the model, session route, Markdown, attachment, or fallback chat. A failed send is not retried by the bridge and does not roll back a commit. Hermes can continue normal dispatch when a hook is absent or its dispatcher fails; never rely on the hook to sandbox the agent or keep chat text out of a model in that case. If the outcome is uncertain, send a new `status` message for the original operation instead of preparing another transaction.

**Linux preflight and installation boundary.** First run the installed-Hermes smoke and Linux isolation probe below. The probe provisions and tears down the bridge's OS boundary in a native Linux temporary directory, using existing Ubuntu fixture UIDs; do not reuse those UID numbers as a deployment recipe. For a future operator-controlled installation on an isolated Linux host or VPS:

1. Use three dedicated non-root accounts: ledger service, trusted gateway, and independent agent runner. Keep the checkout and entry points operator-owned and non-writable to the agent. Use separate homes and no shared mounts, broad groups, sudo, WSL interop, or agent access to the gateway's profile, code, environment, or IPC. If Hermes agent code or tools still execute under the gateway UID, **do not attach the ledger**.
2. Create an empty fictional SQLite fixture as the service UID (`TransactionStore` with an explicit new absolute path), with `umask 077`, directory `0700`, and DB `0600`. Create a separate service-owned socket directory on the same native filesystem with mode `2750` and a dedicated gateway-only group; give the agent no membership. `finance_telegram_ipc.serve(endpoint, ledger, owner=owner_id, gateway_uid=gateway_uid)` is the foreground service entry point, and creates a `0660` socket. Use canonical `Path` objects. Both sides check peer UID. No automatic service installation is supplied.
3. In a reviewed Hermes extension under the trusted gateway account, the wiring contract is `finance_telegram_gateway.register(ctx, owner_id, dispatch, enabled=...)`. The dispatch callback must call `finance_telegram_ipc.request(endpoint, service_uid, envelope)` with operator-fixed settings. Use the real SDK `Message` default, not the test-only `message_class` override. Keep registration disabled and the ledger service disconnected until real SDK identity and effective process isolation pass acceptance. Do not register a tool or point the model at the socket. No deployable plugin, agent-process separation, or live launcher is supplied by this release.
4. On the destination host, verify numeric owner settings and DM-only gates, native filesystem and ownership, service/gateway/agent UIDs, and that the *effective* agent cannot open SQLite/sidecars, read the gateway profile, or connect to the socket. Prove that *only* the gateway UID can request a fictional operation and that the gateway UID itself cannot open SQLite. Repeat after version, config, or host changes. Windows can run the Hermes smoke; neither Windows ACLs nor WSL host interoperability are a verified deployment boundary. A dedicated Linux host is required for financial acceptance; VPS startup/reboot and 2 GB capacity remain unverified.

**Pending live acceptance (separate approval).** First run the baseline-only checks below with a new BotFather test bot, numeric allowlists, and no ledger. Then verify that real private Bot API updates preserve SDK sender, chat, message and update metadata and reject unknown, edited, forwarded, and non-DM messages in a fixture hook that has no IPC access. Verify delivery to the owner and no model fall-through, including busy sessions, pause/drain, and transport failure. Do not proceed to fictional ledger tests unless both that trust check and the effective host isolation above pass. At that point, with separate approval, prepare a fictional expense (example below), inspect the exact JSON, and confirm in a **new** private message (not using Telegram's Reply UI). Try cancel, stale/expired preview, duplicate/concurrent confirm and restart, then verify one matching row locally. No budgets, corrections, Excel, cron, or ledger summary/list is available over this path.

```text
/finance prepare {"transaction_type":"expense","amount_rupiah":25000,"category":"Fiktif","occurred_at":"2026-01-01T12:00:00+07:00"}
/finance confirm <operation_id> <preview_digest>
/finance cancel <operation_id>
/finance status <operation_id>
```

**On any failed security check:** stop the foreground gateway and ledger service, disable/remove the trusted hook entry point, and remove gateway access to the socket before restarting a baseline-only profile with no ledger. A normal Hermes pause is not a substitute for disconnecting IPC. Check the fictional journal privately if a commit may already have happened; revoke the BotFather token if exposed.

### Lesson 8A: finance-only scope

**Verified offline, not enabled.** The stock Hermes setup above is the Lesson 7 baseline, not a finance-only security boundary. In the v0.23.4 source, `pre_gateway_dispatch` falls through on hook errors, and toolset selection does not replace the adapter's native command/media handlers. Project skill trust controls discovery, not execution privileges. The alternative `FinanceScopeTelegramAdapter` reuses the Hermes transport but registers only one update handler on an empty handler table, skips plugin handlers and the generic agent callback, and matches the original private text from the configured numeric owner against a closed list of commands. It has no model, general tools, ledger or report path. It does not load automatically, and the Lesson 7 bridge remains separate.

The help response to `/finance bantuan` lists the exact syntax for fictional calculations. Example inputs: `/finance arus-kas 5000000 3500000`, `/finance anggaran 1500000 900000`, `/finance dana-darurat 3000000 6`, and `/finance target-tabungan 5000000 1000000 1000000`. Supported requests for transaction recording, ledger summaries and Excel are recognized but referred to the local CLI; arbitrary phrasing is not supported. Non-finance and mixed requests receive a refusal without being echoed. There is no live launcher in this lesson. Keep Telegram financial reads, writes and exports disabled until separately approved Bot API acceptance and deployment security checks pass.

With the existing Hermes Python environment and a local checkout or source archive of the upstream `v0.23.4` tag, run `python -B tests/smoke_hermes_telegram_scope.py --hermes-source PATH_TO_HERMES_0_23_4` from this project. The probe verifies the imported adapter path, exercises handler registration and dispatch with SDK stand-ins, and rejects selected network, subprocess and SQLite events via a Python audit hook. It does not start the gateway or prove OS containment, live Bot API delivery, or service behavior. The Windows project regression discovered 111 unit tests (110 passed, 1 POSIX-only cron test skipped).

## 4. Verification (Lessons 7A–7D)

**Offline smoke, no token/SDK/LLM:** run `tests/smoke_hermes_telegram.py` with the Python interpreter from the installed Hermes runtime (not the finance venv). Use the actual executable path for that installation; on a venv-based install it is under `Scripts\python.exe` or `bin/python` in the Hermes venv. On PM-managed Windows installs the active runtime can be under `hermes\installs\…\environments\…\venv`, not the source tree. Keep Python optimization off.

```powershell
& 'C:\path\to\Hermes runtime\Scripts\python.exe' -B tests/smoke_hermes_telegram.py
```

```bash
/path/to/hermes-venv/bin/python -B tests/smoke_hermes_telegram.py
```

The Hermes smoke passed on native Windows using a temporary profile, a non-credential placeholder and a disposable checkout. It retains the Lesson 7A checks for gateway configuration, project skills and the read-only fictional summary. Lesson 7D adds the installed adapter's command handler and runner admission/hook dispatcher with SDK-shaped messages and a recording `send_message` transport. It checks owner admission, stranger rejection, the exact preview's destination and contents, pause/drain, and recovery of a committed Rp25,000 expense after a lost final reply. An audit hook blocks network operations in the adapter probe; the separate config, trust and finance CLI subprocesses do not run under that hook.

The Lesson 7D full regression on Windows discovered 107 tests: 106 passed and one POSIX-only cron test was skipped.

The Ubuntu WSL probe links the trusted callback to the real UID/IPC service through a synthetic gateway port. It verifies preview-before-write, cancel, monotonic expiry, concurrent confirmation, restart/replay, and exactly one Rp25,000 row in a read-only SQLite check. Direct SQLite and IPC access are denied under the fixture agent UID, not an actual deployed Hermes agent. Neither probe calls a model or generates Excel. The probes meet at the same hook contract but are not one running Linux Hermes deployment; the Linux fixture does not require Hermes.

**Future live acceptance, not run by this lesson:** only on a dedicated test host with explicit approval, an empty deployment clone and no scheduled jobs, start `hermes gateway run` in the foreground from the clone with the same profile environment. Do not pass `--replace`, `--force`, `--accept-hooks`, or install a service. From the owner's private chat verify `/whoami` and a harmless fictional simulation using `personal-finance-analysis`; a second account must not get a conversation, pairing code, or data. Verify in BotFather that the bot cannot be added to a group; do not test with shared data or add it to a channel. Verify that a ledger write and administrative slash commands are refused, that the ledger is absent, and that no report/delivery was made. Stop with Ctrl+C and confirm that the foreground process exited. Treat any failed check as a stop condition, not a reason to broaden permissions.

## Troubleshooting and token rotation

| Symptom | Check without broadening access |
| --- | --- |
| No response to the owner | Check the right bot username, profile `.env` path/encoding, numeric owner ID and private chat. Confirm outbound HTTPS and SDK availability on the test host. Check private logs locally without printing token-bearing URLs or transcripts. |
| `409 Conflict` / polling conflict | Stop the duplicate consumer or remove the unintended webhook using official Telegram tooling. Do not run the same token on multiple hosts/profiles or force-replace a different profile. |
| Wrong project or missing skills | Compare `hermes config get terminal.cwd` to the clone root, check Git metadata, trust and toolset in the same profile. Start a fresh session after correcting config; manually reading a `SKILL.md` is not proof of discovery. |
| Extra tools, messages from unknown users, or group replies | Stop the gateway. Check inherited environment, alternate allow/pairing grants, both ID fields, guest mode, BotFather and profile scope. Repeat offline checks and fictional acceptance before restarting. |
| Uncertain write outcome | Stop using chat and check the separate local ledger, operation status or version history. Do not blindly retry or invent a new key. |

For rotation, stop the relevant gateway. In official BotFather revoke the old token (`/revoke`) and obtain the replacement. Replace only that profile's token in the private `.env`; remove stale copies from deployment secret stores and review access/logs if exposure was suspected. Keep the numeric allowlist and group gate in place. Cold boot discards pending updates in this baseline, but do not treat that as transaction protection. Run offline checks and repeat the approved foreground fictional acceptance, then stop the test gateway. Do not restore a revoked token from backup.

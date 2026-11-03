# The `[harness.*]` schema, in full

Everything the body of `harness-config` does not need inline: the whole key census, the
adapter argv table, the complete parser rule list, and worked patterns.

## The full key census

Every harness is a `[harness.<name>]` table. A bare `[<name>]` table still parses for
backward compatibility (ADR-0006), but do not write new ones.

<!-- validate: skip an annotated key census, not a config — it shows the args, prompt and prompt_file branches together, which are mutually exclusive -->
```toml
[harness.my-agent]
harness = "claude-code"          # REQUIRED — enum, no default

# A long-running harness:
args = ["--foo", "bar"]          # appended after the adapter's executable

# ...OR an agent one-shot (mutually exclusive with args):
prompt = "check deployments"     # the instruction; argv is synthesized at spawn
prompt_file = "~/x.md"           # ...or read it from a file (exclusive with prompt)
model = "claude-opus-5"          # requires a prompt
auto_accept = true               # requires a prompt — bypasses ALL permission prompts
max_turns = 20                   # requires a prompt; 0/omitted = unlimited
quiet = false                    # requires a prompt; one-shots are headless by default

# Scheduling (all five require each other's company — see the body):
schedule = "CRON_TZ=UTC 0 3 * * *"
catch_up = true                  # bool: one run on wake, not a replay of every window
timeout = "45m"                  # DURATION STRING; default "1h"; "0" = no limit
on_overlap = "queue"             # skip (default) | queue | replace
keep_runs = 30                   # int >= 1; default 20

# Operating hours (gates a resident harness; mutually exclusive with schedule):
operating_hours = "TZ=America/Los_Angeles Mon-Fri 09:00-13:00"
hours_shutdown = "graceful"      # graceful (default) | immediate — requires operating_hours
hours_shutdown_timeout = "15m"   # DURATION STRING; default "15m" — requires operating_hours

# Applies to either kind:
workdir = "~/src/myproject"      # process working directory
env_file = "~/.config/x.env"     # KEY=VALUE file sourced before launch
description = "My agent"         # shown in the dashboard
enabled = true                   # autostart independent of profiles
restart = "always"               # always | no | unless-stopped | on-failure
restart_delay = 5                # SECONDS, as an integer (contrast timeout)
backend = "native"               # native | tmux
tmux_socket = "/tmp/shared.sock" # inert unless backend = "tmux"
harvest_trajectory = true        # expose transcripts to the facade (default false)
mcp_allow = ["read", "write"]    # facade capability scope (default ["read"])
```

Two types that look alike and are not: **`timeout` is a duration string** (`"45m"`), while
**`restart_delay` is an integer of seconds** (`5`). `timeout = 2700` is a parse error.

## The adapters

`harness` selects an adapter, which owns both the executable a long-running harness runs and
the argv synthesized for a prompt one-shot.

| `harness` | Executable | Prompt argv | `auto_accept` | `max_turns` |
|---|---|---|---|---|
| `crush` | `crush` | `[--yolo] run [--quiet] [--model M] <prompt>` | `--yolo`, **before** `run` (a global flag; after the subcommand crush exits "unknown flag" and the harness crash-loops) | **inert** — crush has no such flag |
| `claude-code` | `claude` | `-p [--dangerously-skip-permissions] [--model M] [--max-turns N] --verbose --output-format stream-json <prompt>` | `--dangerously-skip-permissions` | `--max-turns N` |
| `codex` | `codex` | `exec [--model M] [--full-auto] <prompt>` | `--full-auto` | inert |
| `generic` | `sh` | none — `prompt` is a **config error** (#420) | n/a | n/a |
| `command` | your own `argv` | none — exec'd as written; `prompt` and the agent fields are rejected | n/a | n/a |

`crush`, `claude-code`, `codex`, `generic` and `command` are the five whose argv is above;
main's full census (`core.HarnessKinds`) also accepts `pi`, `omp` and `opencode`, each with its
own synthesis — see `harness.toml.example` in stump.wtf/harness for those.

`generic` runs **`sh`**, so its `args` are sh's args. An arbitrary command is
`args = ["-c", "<command line>"]`. A bare `args = ["/usr/local/bin/thing"]` asks sh to
*interpret* that file as a shell script, which fails on a compiled binary. `command` is the
same job without the shell: `argv = ["/usr/local/bin/thing", "--flag"]`, exec'd directly, with
`{{run.id}}` / `{{run.date}}` placeholders in the elements.

Two argv facts that are easy to get wrong:

- **A `claude-code` one-shot always gets `--verbose --output-format stream-json` appended.**
  Under `-p`, claude rejects `--output-format=stream-json` without `--verbose` and exits 1
  before it reads the prompt — so a hand-written argv that omits `--verbose` does not degrade,
  it never runs, and a scheduled harness reads as a silent no-op.
- **`generic` and `command` have no prompt mode.** `prompt` / `prompt_file` on either is
  rejected at load (#420). It used to fall through to Crush's synthesis, so an operator whose
  adapter was missing from the list got `crush run <prompt>` — or a crash loop naming a binary
  they never configured.

Headless Claude Code auth follows stump.wtf/harness#424: run `claude setup-token` once and put
`CLAUDE_CODE_OAUTH_TOKEN=…` in the harness's `env_file` (mode `0600`) — that bills the operator's
Claude subscription. `ANTHROPIC_API_KEY` works too but bills the **API**; on macOS with the
daemon in the GUI session, the keychain needs nothing at all.

```toml
[harness.tailer]
harness = "generic"
args = ["-c", "tail -F /var/log/app.log"]
```

## Agent fields are config truth, never args

`model`, `auto_accept`, `max_turns`, and `quiet` are stored on the harness and folded into
the synthesized argv **at spawn time** — never desugared into `args` at parse time, because
that would corrupt the TUI edit round-trip.

That is also why they all **require a prompt**: there is no vendor-agnostic place to inject a
flag into an arbitrary command's argv, so a long-running harness passes its tool's flags
through `args` itself.

- `prompt` and `args` are mutually exclusive; so are `prompt` and `prompt_file`.
- `prompt_file` must name a file that **exists** at config load, and must not be blank.
- `model` must be a single token (no whitespace).
- `max_turns` and `restart_delay` must be non-negative.
- `quiet` defaults to `true` for a one-shot; set `false` to stream output to whoever attaches.
- ⚠️ `auto_accept` bypasses **ALL** of the agent's permission prompts. Trusted headless runs only.

## What the parser enforces

`harness --config <path> doctor` prints the parse error with file and line. The rules:

- `harness` present and one of `crush`, `claude-code`, `codex`, `pi`, `omp`, `opencode`,
  `generic`, `command`.
- `cmd` / `agent` rejected with a migration message — they are decoded specifically so their
  presence fails loudly rather than running something unexpected.
- `prompt` / `args` and `prompt` / `prompt_file` mutually exclusive; `model`, `auto_accept`,
  `max_turns`, `quiet`, and `schedule` all require a prompt.
- `catch_up`, `timeout`, `on_overlap`, and `keep_runs` each require `schedule` — rejected on
  *presence*, not only when set to a non-default.
- `prompt` / `prompt_file` on a `generic` or `command` harness is a config error (#420): neither
  kind has prompt synthesis, so nothing is guessed at spawn.
- `operating_hours` must not be blank and is **mutually exclusive with `schedule`**; its
  expression is parsed at load. `hours_shutdown` and `hours_shutdown_timeout` each require
  `operating_hours`, also rejected on *presence*.
- `restart` one of `always`, `no`, `unless-stopped`, `on-failure`; a scheduled harness is
  restricted to `no` or `on-failure`. `backend` one of `native`, `tmux`.
- `keep_runs` >= 1; `timeout` a non-negative duration string.
- Harness names must not contain `/` (reserved for project namespacing).
- Profile members must name existing harnesses, and must not be scheduled.
- Unknown keys are a hard error, not a silent drop.
- Drop-ins: `*.toml` only, `[harness.*]` tables only, no duplicate names, directory must exist.

## Project-scoped config

A repo may carry its own `harness.toml`, discovered by walking up from the working directory.
Project files **reject** the global-only keys: `schedule`, `catch_up`, `timeout`,
`on_overlap`, `keep_runs`, `operating_hours`, `hours_shutdown`, `hours_shutdown_timeout`,
`mcp_allow`, `[profile.*]`, and `[server]`. The three hours keys are in that list for the same
reason `schedule` is: the gate they hang on is daemon-owned, so in a project file they could
only ever parse and then do nothing. They also default `enabled` to **true**, unlike the global
config.

## Trajectory harvesting and the facade

- `harvest_trajectory` (default `false`) exposes this harness's transcripts read-only to the
  MCP facade. Opt-in, because a transcript may contain secrets the harnessed program printed.
- `mcp_allow` (default `["read"]`) is the facade capability scope. **It grants access to
  nothing that exists today**: the facade defines only `list_trajectories` and
  `get_trajectory` (both read-class), and no MCP transport serves them. The write trio
  (`harness_start` / `harness_stop` / `harness_restart`) appears only in doc comments as
  planned work. `mcp_allow = []` is a real value meaning "no facade access at all" — do not
  drop it when rewriting a table. Global config only.

## Operating hours and the after-hours lease

`operating_hours` gates a **resident** harness to the weekly windows in which it may run. Outside
them the daemon holds it down without touching `enabled`, so `harness list` reads **`off-hours`**
(amber) where an ungated harness would read `stopped`.

```toml
[harness.night-owl]
harness = "claude-code"
args = ["--remote-control", "--continue"]
enabled = true
operating_hours = "TZ=America/Los_Angeles Mon-Fri 09:00-13:00"
hours_shutdown = "graceful"           # graceful (default) | immediate
hours_shutdown_timeout = "15m"        # default "15m"; a positive duration string
```

- **Syntax:** an optional zone prefix — `TZ=<zone>` or `CRON_TZ=<zone>`, the same prefixes
  `schedule` accepts — then `"days HH:MM-HH:MM"` windows. A day range
  wraps the week (`Fri-Mon` is Fri/Sat/Sun/Mon), a day-less window applies every day, and an end
  at or before its start (other than the explicit end-of-day `24:00`) runs into the next day.
  A bad expression fails the load with a located error.
- **The close:** `hours_shutdown = "graceful"` (the default) waits for the agent to finish its
  current turn, capped by `hours_shutdown_timeout` (`15m` default); `"immediate"` stops it at
  once. While a graceful close is in flight the state reads `closing`, which outranks
  `off-hours`.
- **A late night:** `harness start <name>` outside the window runs it under a **one-hour
  after-hours lease**, or `harness start <name> --for 3h` for a longer one. Its `NEXT` column
  then reads `lease until <time>` — distinct from both `off-hours` (held) and `closing`. The
  gate ends the run at the lease's expiry exactly as it would at a close; `harness stop <name>`
  ends the lease early and clears `enabled`, in hours or out.
- **Exclusions:** `schedule` and `operating_hours` are mutually exclusive (a scheduled one-shot
  is already time-gated by its own cron expression); `hours_shutdown` and
  `hours_shutdown_timeout` require `operating_hours`; a project file or drop-in setting any of
  the three is refused. On a harness with `triggers` the window gates **firings**, not the
  process: an out-of-hours event is recorded `skipped` with reason `outside_hours` (a burst
  coalesces into one record), a run in flight at the close finishes under its `timeout`, and
  `catch_up = true` starts one run when hours next open. `harness trigger <name>` is never
  gated: the manual verb asks the daemon for exactly one run (`opTrigger`), and the hours gate
  lives only in the scheduler pass and the event fan-out — nothing on that path consults the
  window, which is what makes it the deliberate out-of-hours escape hatch.

## Worked patterns

### Scheduled unattended job (drop-in)

```toml
# ~/.config/harness/harness.d/deploy-check.toml
[harness.deploy-check]
harness = "claude-code"
prompt = "check if any deployments are stuck or failing"
model = "claude-opus-5"
auto_accept = true
max_turns = 20
schedule = "CRON_TZ=UTC */15 * * * *"
timeout = "10m"
on_overlap = "skip"
restart = "on-failure"
description = "deploy watchdog (every 15m)"
```

### Interactive development agent

```toml
[harness.dev-agent]
harness = "crush"
workdir = "~/src/myproject"
description = "Development assistant for myproject"
```

### Arbitrary long-running command

```toml
[harness.log-tail]
harness = "generic"
args = ["-c", "tail -F /var/log/app.log"]
description = "app log tail"
restart = "always"
restart_delay = 5
```

### Two agents, different models

```toml
[harness.fast-reviewer]
harness = "crush"
prompt = "review the latest PR and summarize findings"
model = "zai/glm-5.3"
schedule = "0 9 * * *"
auto_accept = true
restart = "on-failure"
```

```toml
[harness.deep-analyst]
harness = "claude-code"
prompt = "analyze the architecture of this codebase and suggest improvements"
model = "claude-opus-5"
max_turns = 60
schedule = "0 7 * * 1"
keep_runs = 50
auto_accept = true
restart = "on-failure"
```

### Profiles

Profiles are named groups switched together. Global config only — never in a project file or
a drop-in. Members may name drop-in harnesses; they may **not** name a scheduled harness.

<!-- validate: stub dev-agent,inbox-triage -->
```toml
[profile.morning]
description = "Morning routine agents"
harnesses = ["dev-agent", "inbox-triage"]
autostart = true
```

### Daemon settings

```toml
[daemon]
watch_config = true                          # auto-reload on harness.toml change (default true)

[telemetry]
traces = true                                # OTLP traces, one per agent session (default false)
endpoint = "http://127.0.0.1:4318"          # OTLP/HTTP base; /v1/logs and /v1/traces are appended
```

`watch_config` watches `harness.toml` only — **not** `harness_d` drop-ins. The old
`otel_endpoint` key in `[daemon]` is gone (migration note, not a supported key): agent
telemetry now lives in a `[telemetry]` table.

### Merge train

`[mergetrain]` lands reviewed PRs by train (ADR-0032). It is **global-only**: a project file
or a drop-in that enables it is refused.

| Key | Type | Notes |
|---|---|---|
| `enabled` | bool | |
| `mode` | `"report"` \| `"merge"` | any other value is a load error |
| `repos` | list of `"owner/name"` | an entry that is not `owner/name` fails the load |
| `base_branch` | string | |
| `poll_interval`, `ci_timeout`, `flake_cool_down` | duration strings | each has a minimum; an explicit zero is refused |
| `batch` | int ≥ 1 | |
| `forge_base_url` | string | absolute http(s) URL with a host |
| `forge_token_env` | string | the **name** of an env var, never the token |

A `token` key is refused outright — a forge token is a credential (ADR-0008), so it lives in
the daemon's environment and the config only names the variable.


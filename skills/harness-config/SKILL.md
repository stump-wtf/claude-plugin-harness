---
name: harness-config
description: >
  Author, edit, and review configuration for harness — the agent supervisor
  (https://gitea.stump.rocks/stump.wtf/harness). Use whenever a request touches
  harness config: "add a harness", "schedule an agent", "set up crush/claude-code
  as a harness", "why won't my harness.toml load", editing `harness.toml` or a
  drop-in under a `harness.d` directory, or reviewing an existing config. Covers
  the required `harness` enum, agent one-shots (prompt/model/auto_accept/
  max_turns/quiet), cron scheduling, profiles, MCP facade scoping, and the
  `harness_d` drop-in directory — including the rule that decides whether a new
  harness goes in the main file or its own file.
---

# Harness Config

Configuration for [harness](https://gitea.stump.rocks/stump.wtf/harness), the
agent supervisor. Reference docs:
https://stump-wtf.pages.stump.rocks/harness/usage/configuration

**Two things to do before writing anything, every time:**

1. **Read the existing config** and check for `[server] harness_d`. It decides
   *where* a new harness goes — see [Where a new harness goes](#where-a-new-harness-goes).
   Getting this wrong is not a style question: it puts the harness in a file
   nobody is reading.
2. **Validate what you wrote** with `harness --config <path> doctor`. The parser
   rejects far more than it used to, with a located error. Never hand back a
   config you have not run through it. Note the flag goes **before** the verb —
   `doctor --config` is a newer spelling that older builds reject.

## Where a new harness goes

`harness_d` is a directory of drop-in files. When it is configured, **each
harness gets its own file** — that is the entire point of the directory, and
appending to the main `harness.toml` instead defeats it.

> ⚠️ **`harness_d` needs a build newer than v0.3.0.** It is unreleased at time
> of writing. On v0.3.0 the key is **silently ignored** — the config still
> reports `ok`, and every drop-in harness is simply absent. The only symptom is
> indirect: a main-file profile naming one fails with `references unknown
> harness "…"`. Confirm with `harness --version` before recommending drop-ins;
> if the operator is on v0.3.0, write to the main file instead and say why.

```bash
# 1. Find the config the daemon is actually using.
harness doctor | grep -A1 '^config'          # or: harness --config <path> doctor

# 2. Is a drop-in directory configured?
grep -n 'harness_d' ~/.config/harness/harness.toml
```

| What you find | Where the new harness goes |
|---|---|
| `[server] harness_d = "…"` is set | `<harness_d>/<name>.toml`, **one harness per file** |
| No `harness_d` key | a new `[harness.<name>]` table appended to `harness.toml` |

When writing a drop-in:

- **Name the file after the harness**: `deploy-check` → `deploy-check.toml`. The
  loader does not care, but a human deleting a harness should not have to grep
  for it.
- **Only `[harness.*]` tables.** `[server]`, `[profile.*]`, `[daemon]`, and bare
  `[name]` tables are rejected with the offending file and line. A profile that
  should include a drop-in harness goes in the **main** file — main-file
  profiles may reference drop-in harnesses, and that ordering is deliberate.
- **One harness per file.** Several `[harness.*]` tables in one drop-in parse
  fine, but then removing a harness means editing a file instead of deleting
  one.
- **Create the directory if it does not exist.** A missing `harness_d` is a hard
  config-load failure, not an empty directory — deliberately, so a typo cannot
  silently drop every drop-in.
- **Reload afterwards.** Drop-ins are **not** watched: `watch_config` watches
  `harness.toml` only, so a new file is invisible until `harness reload` (or a
  touch of the main config).

Setting the directory up in the first place:

<!-- validate: skip resolves against a real home directory, which a runner has no reason to have -->
```toml
# ~/.config/harness/harness.toml
[server]
harness_d = "~/.config/harness/harness.d"
```

```toml
# ~/.config/harness/harness.d/deploy-check.toml
[harness.deploy-check]
harness = "claude-code"
prompt = "check if any deployments are stuck or failing"
auto_accept = true
schedule = "*/15 * * * *"
restart = "on-failure"
```

Details that decide behavior:

- A leading `~` expands to the home directory; a **relative path resolves
  against the directory holding `harness.toml`**, not the daemon's working
  directory (under systemd those differ).
- Only `*.toml` files are read; everything else in the directory is ignored.
- Files merge in lexicographic order. Prefix with `10-`, `20-` only if you
  actually care about order — plain names are the norm.
- Duplicate harness names — between two drop-ins, or with the main file — are
  rejected rather than silently overwritten.

## Config location

Default `$XDG_CONFIG_HOME/harness/harness.toml` (usually
`~/.config/harness/harness.toml`), overridable per verb with `--config`. A repo
may also carry a project-scoped `harness.toml`; project files reject the
global-only keys (`schedule`, `mcp_allow`, `[profile.*]`, `[server]`).

## Harness table schema

Every harness is a `[harness.<name>]` table. A bare `[<name>]` table still
parses for backward compatibility, but do not write new ones.

<!-- validate: skip an annotated key census, not a config — it shows the args and prompt branches together, which are mutually exclusive -->
```toml
[harness.my-agent]
harness = "claude-code"          # REQUIRED — enum, no default (see below)

# A long-running harness:
args = ["--foo", "bar"]          # appended after the adapter's executable

# ...OR an agent one-shot (mutually exclusive with args):
prompt = "check deployments"     # the instruction; argv is synthesized at spawn
model = "claude-opus-5"          # requires prompt
auto_accept = true               # requires prompt — bypasses ALL permission prompts
max_turns = 20                   # requires prompt; 0/omitted = unlimited
quiet = false                    # requires prompt; one-shots are headless by default
schedule = "0 */6 * * *"         # requires prompt; standard 5-field cron

# Applies to either kind:
workdir = "~/src/myproject"      # process working directory
env_file = "~/.config/x.env"     # KEY=VALUE file sourced before launch
description = "My agent"         # shown in the dashboard
enabled = true                   # autostart independent of profiles
restart = "always"               # always | no | unless-stopped | on-failure
restart_delay = 5                # seconds between exit and respawn
backend = "native"               # native | tmux
tmux_socket = "/tmp/shared.sock" # tmux server socket; inert unless backend = "tmux"
harvest_trajectory = true        # expose transcripts read-only over MCP (default false)
mcp_allow = ["read", "write"]    # MCP facade capability scope (default ["read"])
```

### `harness` is required, and `cmd` is gone

This is the change that breaks every pre-0.3 config and every example written
before it:

<!-- validate: expect-fail -->
```toml
# WRONG — hard parse error, not a warning
[harness.dev-agent]
cmd = "crush"
```

```toml
# RIGHT
[harness.dev-agent]
harness = "crush"
```

```
harness "dev-agent": "cmd" was replaced by the "harness" enum — set
harness = "crush"|"claude-code"|"codex" for an agent, or harness = "generic"
with args = ["-c", "crush"] to run an arbitrary command
```

`agent = ` was likewise renamed to `harness = `. Both removed keys are still
decoded specifically so their presence **fails loudly** rather than being
ignored and silently running something else.

There is no default. An omitted `harness` key is an error:

```
harness "web": missing required key "harness" (want one of: crush, claude-code,
codex, generic — use "generic" with args = ["-c", "…"] for an arbitrary command)
```

### The adapters

`harness` selects an adapter, which owns both the executable a long-running
harness runs and the argv synthesized for a prompt one-shot.

| `harness` | Executable | Prompt argv | `auto_accept` | `max_turns` |
|---|---|---|---|---|
| `crush` | `crush` | `[--yolo] run [--quiet] [--model M] <prompt>` | `--yolo`, **before** `run` (it is a global flag; after the subcommand crush exits "unknown flag" and the harness crash-loops) | **inert** — crush has no such flag at any position |
| `claude-code` | `claude` | `-p [--dangerously-skip-permissions] [--model M] [--max-turns N] --output-format stream-json <prompt>` | `--dangerously-skip-permissions` | `--max-turns N` |
| `codex` | `codex` | `exec [--model M] [--full-auto] <prompt>` | `--full-auto` | inert |
| `generic` | `sh` | n/a — no prompt synthesis | n/a | n/a |

`generic` runs **`sh`**, so its `args` are sh's args. An arbitrary command is
`args = ["-c", "<command line>"]`. A bare `args = ["/usr/local/bin/thing"]` asks
sh to *interpret* that file as a shell script, which fails on a compiled binary.

```toml
[harness.tailer]
harness = "generic"
args = ["-c", "tail -F /var/log/app.log"]
```

### Agent fields are config truth, never args

`model`, `auto_accept`, `max_turns`, and `quiet` are stored on the harness and
folded into the synthesized argv **at spawn time** — they are never desugared
into `args` at parse time, because that would corrupt the TUI edit round-trip.

That is also why they all **require `prompt`**: there is no vendor-agnostic
place to inject a flag into an arbitrary command's argv, so a long-running
harness passes its tool's flags through `args` itself.

- `prompt` and `args` are mutually exclusive.
- `model` must be a single token (no whitespace).
- `max_turns` must be non-negative.
- `quiet` defaults to `true` for a one-shot; set `false` to stream output to
  whoever attaches.
- ⚠️ `auto_accept` bypasses **ALL** of the agent's permission prompts. Only on
  trusted, headless runs.

## Scheduled one-shots

Give a prompt harness a `schedule` and the daemon fires it on that cadence:

```toml
[harness.stumpcloud-sweep]
harness = "claude-code"
prompt = "check all services and report anything unhealthy"
model = "claude-opus-5"
auto_accept = true
schedule = "0 */6 * * *"   # standard 5-field cron, daemon's local time
description = "scheduled sweep (every 6h)"
restart = "on-failure"
```

Validated at config load:

- Requires `prompt` — only agent one-shots can be scheduled.
- Standard 5-field cron. `@daily`-style descriptors are **not** accepted.
- Mutually exclusive with `enabled = true`.
- Mutually exclusive with profile membership — a profile autostart would fire it
  outside its schedule.
- `restart` restricted to `"no"` (the prompt default) or `"on-failure"`;
  `always`/`unless-stopped` would respawn the one-shot after a clean exit.
- Global config only — project files reject the key.
- If the harness is already running at a firing, that firing is **skipped, not
  stacked**.

Keep long instructions in a file and point the prompt at it, so prompt edits do
not touch the schedule:

```toml
[harness.my-sweep]
harness = "claude-code"
prompt = "Read ~/.config/my-sweep.prompt.md and execute its instructions verbatim."
schedule = "30 9 * * *"
```

## Trajectory harvesting & MCP facade scope

- `harvest_trajectory` (default `false`) exposes this harness's transcripts
  read-only through the MCP facade (`list_trajectories` / `get_trajectory`).
  Opt-in, because a transcript may contain secrets the harnessed program printed
  itself.
- `mcp_allow` (default `["read"]`) is the facade capability scope; add
  `"write"` to permit `harness_start` / `harness_stop` / `harness_restart`.
  `mcp_allow = []` is a real value meaning "no facade access at all" — do not
  drop it when rewriting a table. **Global config only**: project files reject
  the key, so a cloned repo cannot grant itself write authority over the fleet.

## Profiles

Profiles are named groups switched together. Global config only — never in a
project file or a drop-in.

<!-- validate: stub dev-agent,inbox-triage -->
```toml
[profile.morning]
description = "Morning routine agents"
harnesses = ["dev-agent", "inbox-triage"]
autostart = true
```

Members may name harnesses defined in `harness_d` drop-ins. Members may **not**
name a scheduled harness.

## Daemon settings

```toml
[daemon]
watch_config = true                          # auto-reload on harness.toml change (default true)
otel_endpoint = "https://cairn.stump.wtf"    # OTLP/HTTP trace export (optional)
```

`watch_config` watches `harness.toml` only — **not** `harness_d` drop-ins.

## Validate before you hand it back

```bash
harness --config ~/.config/harness/harness.toml doctor
harness reload      # picks up drop-ins, which are not watched
```

`doctor` prints the parse error with file and line. What the parser enforces:

- `harness` present and one of `crush`, `claude-code`, `codex`, `generic`.
- `cmd` / `agent` rejected with a migration message.
- `prompt` and `args` mutually exclusive; `model`, `auto_accept`, `max_turns`,
  `quiet`, and `schedule` all require `prompt`.
- `restart` one of `always`, `no`, `unless-stopped`, `on-failure`; `backend` one
  of `native`, `tmux`.
- `restart_delay` and `max_turns` non-negative; `model` a single token.
- Harness names must not contain `/` (reserved for project namespacing).
- Profile members must name existing harnesses, and must not be scheduled.
- Unknown keys are a hard error, not a silent drop.
- Drop-ins: `*.toml` only, `[harness.*]` tables only, no duplicate names, and
  the directory must exist.

## Common patterns

### Scheduled unattended job (drop-in)

```toml
# ~/.config/harness/harness.d/deploy-check.toml
[harness.deploy-check]
harness = "claude-code"
prompt = "check if any deployments are stuck or failing"
model = "claude-opus-5"
auto_accept = true
max_turns = 20
schedule = "*/15 * * * *"
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
# ~/.config/harness/harness.d/fast-reviewer.toml
[harness.fast-reviewer]
harness = "crush"
prompt = "review the latest PR and summarize findings"
model = "zai/glm-5.3"
schedule = "0 9 * * *"
auto_accept = true
restart = "on-failure"
```

```toml
# ~/.config/harness/harness.d/deep-analyst.toml
[harness.deep-analyst]
harness = "claude-code"
prompt = "analyze the architecture of this codebase and suggest improvements"
model = "claude-opus-5"
max_turns = 60
schedule = "0 7 * * 1"
auto_accept = true
restart = "on-failure"
```

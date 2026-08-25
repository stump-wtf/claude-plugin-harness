---
name: harness-config
description: Author, edit, and review harness.toml configuration files for the harness agent supervisor — adding or updating harness definitions, wiring up agent CLIs (Crush, Claude Code, Codex, Aider) as harnesses, and questions about harness config fields or syntax.
user-invocable: true
---

# Harness Config

Skill for authoring and editing `harness.toml` configuration files for the [harness](https://gitea.stump.rocks/stump.wtf/harness) agent supervisor.

## When to use

- User asks to create, edit, or review a `harness.toml` file
- User wants to add a new harness definition
- User asks about harness config fields or syntax
- User wants to set up an agent CLI (Crush, Claude Code, Codex, Aider) as a harness

## Config location

Default: `$XDG_CONFIG_HOME/harness/harness.toml` (typically `~/.config/harness/harness.toml`).

## Harness table schema

Each harness is a `[harness.<name>]` table (or bare `[<name>]` for backward compatibility):

```toml
[harness.my-agent]
# Required (one of):
cmd = "crush"                    # executable to run
# OR
prompt = "check deployments"     # agent one-shot shorthand (sets cmd=crush, args=["run","--quiet",prompt])

# Optional:
args = ["run", "--quiet"]        # command arguments
model = "claude-opus-5"          # appends --model <value> to the run argv (crush: provider/model syntax)
auto_accept = true               # prepends the GLOBAL --yolo flag, before the run subcommand
max_turns = 10                   # turn budget; crush has no --max-turns yet, so it is logged-and-dropped (inert, not fatal)
quiet = true                     # appends --quiet to args (suppresses TUI output)
workdir = "~/src/myproject"      # process working directory
env_file = ".env"                # KEY=VALUE file sourced before launch
description = "My agent"         # shown in TUI list
enabled = true                   # autostart independent of profiles
schedule = "0 */6 * * *"         # 5-field cron; fires this prompt harness on schedule
restart = "always"               # always | no | unless-stopped | on-failure
restart_delay = 5                # seconds between crash and respawn
backend = "native"               # native | tmux
tmux_socket = ""                 # tmux socket name (only for backend=tmux)
```

## Agent abstraction fields

These fields translate to agent CLI flags at parse time, making the config declarative instead of requiring raw flag knowledge:

| Field | Flag appended | Purpose |
|---|---|---|
| `prompt` | Synthesizes `cmd=crush args=["--yolo"?,"run","--quiet",<prompt>]` | One-shot agent instruction |
| `model` | `--model <value>` after `run` | Model selection (crush wants `provider/model`, e.g. `zai/glm-5.3`) |
| `auto_accept` | `--yolo` BEFORE `run` (global flag; after the subcommand crush rejects it and the harness crash-loops) | Skip permission prompts |
| `max_turns` | none on crush (no such flag at any position; issue open) — inert, kept on the wire | Budget cap for unattended runs (honored by the claude adapter's `--max-turns`) |
| `quiet` | `--quiet` after `run` | Suppress interactive output |

### Constraints

- `prompt` and `cmd` are **mutually exclusive** — setting both is a parse error
- `prompt` with no `cmd` defaults to `cmd = "crush"` with `args = ["run", "--quiet", <prompt>]`
- `max_turns` must be non-negative; negative values are rejected
- `auto_accept` and `quiet` use pointer semantics: absent means false, explicit `false` is respected

## Scheduled harnesses

Any `prompt` harness can run on a cron schedule via `schedule`:

```toml
[harness.stumpcloud-sweep]
prompt = "check all services and report anything unhealthy"
schedule = "0 */6 * * *"   # 5-field cron (minute hour dom month dow), daemon's local time
auto_accept = true
model = "zai/glm-5.3"
description = "scheduled sweep (every 6h)"
restart = "on-failure"
```

Rules (validated at config load):

- Requires `prompt` — `schedule` applies only to agent one-shots, never `cmd` harnesses (error: `"schedule" requires "prompt"`)
- 5-field cron only; `@daily`-style descriptors are NOT accepted
- Mutually exclusive with `enabled = true` (scheduled harnesses are never autostarted — the cron is the only trigger)
- Mutually exclusive with profile membership (a profile autostart would fire it outside its schedule)
- `restart` restricted to `"no"` or `"on-failure"` — `always`/`unless-stopped` would respawn the one-shot after a clean exit and make the schedule meaningless
- Not supported in project files (`.harness.toml`) — global config only
- If the harness is already running at a firing time, that firing is **skipped, not stacked**

Pattern: keep the long instructions in a managed file and point the prompt at it, so prompt edits propagate without touching the schedule:

```toml
[harness.my-sweep]
prompt = "Read ~/.config/my-sweep.prompt.md and execute its instructions verbatim."
schedule = "30 9 * * *"
```

## Common patterns

### Cron job (unattended, budgeted)

```toml
[harness.deploy-check]
prompt = "check if any deployments are stuck or failing"
model = "zai/glm-5.3"
auto_accept = true
schedule = "*/15 * * * *"
restart = "on-failure"
```

### Interactive development agent

```toml
[harness.dev-agent]
cmd = "crush"
workdir = "~/src/myproject"
description = "Development assistant for myproject"
```

### Multiple agents with different models

```toml
[harness.fast-reviewer]
prompt = "review the latest PR and summarize findings"
model = "zai/glm-5.3"
schedule = "0 9 * * *"
auto_accept = true
restart = "on-failure"

[harness.deep-analyst]
prompt = "analyze the architecture of this codebase and suggest improvements"
model = "claude-opus-5"
schedule = "0 7 * * 1"
auto_accept = true
restart = "on-failure"
```

## Profiles

Profiles group harnesses for batch operations:

```toml
[profile.morning]
description = "Morning routine agents"
harnesses = ["deploy-check", "inbox-triage"]
autostart = true
```

## Validation

The parser validates at load time:
- Either `cmd` or `prompt` must be set (not both, not neither)
- `restart` must be one of: `always`, `no`, `unless-stopped`, `on-failure`
- `backend` must be `native` or `tmux`
- `restart_delay` and `max_turns` must be non-negative
- Harness names must not contain `/` (reserved for project namespacing)
- Profile members must reference existing harness names
- `schedule` requires `prompt`, rejects `@`-descriptors, excludes `enabled = true` and profile membership, restricts `restart` to `no`/`on-failure`, and is rejected in project files

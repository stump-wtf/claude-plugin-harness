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
model = "claude-opus-5"          # appends --model <value> to args
auto_accept = true               # appends --yolo to args (bypasses permission prompts)
max_turns = 10                   # appends --max-turns <value> to args (budget cap)
quiet = true                     # appends --quiet to args (suppresses TUI output)
workdir = "~/src/myproject"      # process working directory
env_file = ".env"                # KEY=VALUE file sourced before launch
description = "My agent"         # shown in TUI list
enabled = true                   # autostart independent of profiles
restart = "always"               # always | no | unless-stopped | on-failure
restart_delay = 5                # seconds between crash and respawn
backend = "native"               # native | tmux
tmux_socket = ""                 # tmux socket name (only for backend=tmux)
```

## Agent abstraction fields

These fields translate to agent CLI flags at parse time, making the config declarative instead of requiring raw flag knowledge:

| Field | Flag appended | Purpose |
|---|---|---|
| `prompt` | Synthesizes `cmd=crush args=["run","--quiet",<prompt>]` | One-shot agent instruction |
| `model` | `--model <value>` | Model selection |
| `auto_accept` | `--yolo` | Skip permission prompts |
| `max_turns` | `--max-turns <value>` | Budget cap for unattended runs |
| `quiet` | `--quiet` | Suppress interactive output |

### Constraints

- `prompt` and `cmd` are **mutually exclusive** — setting both is a parse error
- `prompt` with no `cmd` defaults to `cmd = "crush"` with `args = ["run", "--quiet", <prompt>]`
- `max_turns` must be non-negative; negative values are rejected
- `auto_accept` and `quiet` use pointer semantics: absent means false, explicit `false` is respected

## Common patterns

### Cron job (unattended, budgeted)

```toml
[harness.deploy-check]
prompt = "check if any deployments are stuck or failing"
model = "claude-sonnet-4"
auto_accept = true
max_turns = 5
restart = "no"
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
model = "claude-sonnet-4"
max_turns = 3
auto_accept = true
restart = "no"

[harness.deep-analyst]
prompt = "analyze the architecture of this codebase and suggest improvements"
model = "claude-opus-5"
max_turns = 20
auto_accept = true
restart = "no"
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

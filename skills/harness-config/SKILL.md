---
name: harness-config
description: >
  Author, edit, and review configuration for harness — the agent supervisor
  (https://stump-wtf.github.io/harness/). Use whenever a request touches harness
  config: "add a harness", "schedule an agent", "run it in UTC", "set up
  crush/claude-code as a harness", "why won't my harness.toml load", editing
  `harness.toml` or a drop-in under a `harness.d` directory, or reviewing an
  existing config. Covers the required `harness` enum, agent one-shots
  (prompt/prompt_file/model/auto_accept/max_turns/quiet), cron scheduling with
  time zones, the run controls (catch_up, timeout, on_overlap, keep_runs), operating
  hours with the after-hours lease,
  profiles, and the `harness_d` drop-in directory — including the rule that
  decides whether a new harness goes in the main file or its own file.
---

# Harness Config

Configuration for [harness](https://stump-wtf.github.io/harness/), the agent supervisor.
Reference docs: https://stump-wtf.github.io/harness/usage/configuration/

**Two things to do before writing anything, every time:**

1. **Read the existing config** and check for `[server] harness_d` — it decides *where* a new
   harness goes (below). Getting it wrong puts the harness in a file nobody reads.
2. **Validate what you wrote** with `harness --config <path> doctor`; never hand back a config
   you have not run it on.

## Where a new harness goes

`harness_d` is a directory of drop-in files. When it is configured, **each harness gets its
own file** — appending to the main `harness.toml` instead defeats the point of it.

> ⚠️ **`harness_d` landed in v0.4.0.** On an older release the key is **silently ignored**: config
> reports `ok`, every drop-in harness is absent, and a main-file profile naming one fails with
> `references unknown harness "…"`. Check `harness --version`; on an older build, use the main file.

```bash
harness doctor | grep -A1 '^config'          # which config is the daemon using?
grep -n 'harness_d' ~/.config/harness/harness.toml
```

| What you find | Where the new harness goes |
|---|---|
| `[server] harness_d = "…"` is set | `<harness_d>/<name>.toml`, **one harness per file** |
| No `harness_d` key | a new `[harness.<name>]` table appended to `harness.toml` |

Note `harness_d` lives under **`[server]`**, not `[daemon]` — counter-intuitive, and a
frequent mis-edit.

When writing a drop-in:

- **Name the file after the harness**: `deploy-check` → `deploy-check.toml`.
- **Only `[harness.*]` tables.** `[server]`, `[profile.*]`, `[daemon]`, and bare `[name]`
  tables are rejected with the offending file and line. A profile that should include a
  drop-in harness goes in the **main** file; that ordering is deliberate.
- **Create the directory if it does not exist.** A missing `harness_d` is a hard config-load
  failure, so a typo cannot silently drop every drop-in.
- **Reload afterwards.** Drop-ins are **not** watched: `watch_config` watches `harness.toml`
  only, so a new file is invisible until `harness reload`.
- A leading `~` expands to the home directory; a **relative path resolves against the
  directory holding `harness.toml`**, not the daemon's working directory. Only `*.toml` is
  read; files merge lexicographically; duplicate names are rejected.

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

## Config location

Default `$XDG_CONFIG_HOME/harness/harness.toml` (usually `~/.config/harness/harness.toml`),
overridable with `--config`. A missing file is **not** an error. A repo may also carry a
project-scoped `harness.toml`, which rejects the global-only keys (`schedule`, the run controls,
the operating-hours keys, `mcp_allow`).

## `harness` is required, and `cmd` is gone

This is the change that breaks every pre-0.3 config and every example written before it:

<!-- validate: expect-fail -->
```toml
# WRONG — hard parse error, not a warning
[harness.dev-agent]
cmd = "crush"
```

```toml
[harness.dev-agent]
harness = "crush"
```

`agent = ` was likewise renamed to `harness = `. Both removed keys are still decoded so their
presence **fails loudly** rather than silently running something else. There is no default —
an omitted `harness` key is an error naming the valid values (`crush`, `claude-code`, `codex`,
`pi`, `omp`, `opencode`, `generic`, `command`).

A harness is then **either** long-running (`args`) **or** an agent one-shot (`prompt`, or
`prompt_file` naming a file that exists). Those are mutually exclusive, and `model`,
`auto_accept`, `max_turns`, `quiet`, and `schedule` all require a prompt. `generic` and
`command` have **no prompt mode**: a `prompt` on either is a config error (#420), not the
fall-through to Crush it used to be. The full key census, the adapter argv table, and every
parser rule are in `references/schema.md` (resolve it against this skill's own directory).

## Scheduled one-shots

Give a prompt harness a `schedule` and the daemon fires it on that cadence:

```toml
[harness.stumpcloud-sweep]
harness = "claude-code"
prompt = "check all services and report anything unhealthy"
model = "claude-opus-5"
auto_accept = true
schedule = "CRON_TZ=UTC 0 */6 * * *"
catch_up = true
timeout = "45m"
on_overlap = "queue"
keep_runs = 30
description = "scheduled sweep (every 6h)"
restart = "on-failure"
```

**Cron forms.** Standard 5-field expressions, **and** descriptors — `@daily`, `@hourly`,
`@every 6h` all parse (older guidance claiming descriptors are rejected is wrong).

**Time zones.** A bare expression runs in the daemon's **local** zone, so the same drop-in on
two machines fires at two different absolute times. Prefix it with `CRON_TZ=<zone>` (or
`TZ=<zone>`) to pin it: `schedule = "CRON_TZ=America/New_York 30 2 * * *"`. An unknown zone is a
load error; descriptors take the prefix too (`CRON_TZ=UTC @daily`).

### The four run controls

All four require `schedule`, and are rejected on *presence* without one.

| Key | Type | Default | Means |
|---|---|---|---|
| `catch_up` | bool | `false` | On wake or boot after missed windows, run **once** — not once per window. `false` logs a `missed` record covering them all. |
| `timeout` | **duration string** | `"1h"` | SIGTERM then SIGKILL; the run is `timed_out`. `"0"` = no limit. |
| `on_overlap` | string | `"skip"` | A firing landing mid-run: `skip` records it, `queue` holds **one**, `replace` stops the run in flight. |
| `keep_runs` | int ≥ 1 | `20` | Run records (and their logs) retained. |

`timeout` is a **string**; `restart_delay` is an integer of seconds. Mixing them up is the
most common error here:

<!-- validate: expect-fail -->
```toml
# WRONG — timeout is a duration string, not seconds
[harness.sweep]
harness = "claude-code"
prompt = "sweep"
schedule = "0 3 * * *"
timeout = 2700
```

**Operating hours.** `operating_hours = "TZ=<zone> Mon-Fri 09:00-13:00"` gates a **resident**
harness to weekly windows instead of firing it: outside them it reads `off-hours`, and
`harness start <name> --for 3h` runs it under an after-hours lease anyway. It is mutually
exclusive with `schedule`, and `hours_shutdown` / `hours_shutdown_timeout` require it. Window
syntax, the lease, and the `closing` state: `references/schema.md`.

Also validated at load: a schedule requires a prompt; it is mutually exclusive with
`enabled = true` and with profile membership; `restart` is restricted to `"no"` or
`"on-failure"`; and the key is global-config only. Keep long instructions in a file
(`prompt_file`) so prompt edits do not touch the schedule.

## Merge train ([mergetrain])

A **global-only** table that lands reviewed PRs by train (ADR-0032); its keys are in
`references/schema.md`.

## Validate before you hand it back

`harness --config <path> doctor` prints the parse error with file and line; unknown keys are a hard error, not a silent drop. See what a scheduled harness will actually do with `harness jobs` and `harness runs <name>`. Reload to pick up drop-ins, which are not watched.

## References

Resolve against this skill's own directory.

- `references/schema.md` — the full `[harness.*]` key census, the adapter argv table, every
  parser rule, project-scoped restrictions, operating hours and the after-hours lease, the
  `[mergetrain]` keys, the facade/`mcp_allow` reality, and worked patterns.

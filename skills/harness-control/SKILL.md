---
name: harness-control
description: Operate a RUNNING harness daemon from the command line — inspect state, start/stop/restart a harness, read logs, spawn a throwaway agent run, and escalate work from one agent to another. Use when a request is about running harnesses rather than configuring them ("what agents are running", "restart the sweep", "kick off an agent to do X", "escalate this to a bigger model", "why did my scheduled harness not fire"). For authoring harness.toml itself, use harness-config instead.
user-invocable: true
---

# Harness Control

Operating a live [harness](https://gitea.stump.rocks/stump.wtf/harness) daemon. This is the runtime half; `harness-config` is the authoring half.

The CLI **is** the supported programmatic surface (ADR-0002), and `--json` is a first-class contract on it. There is no MCP server and no HTTP API — do not go looking for one.

## When to use

- Inspecting what is running: "what agents are up", "is the sweep still going"
- Lifecycle: start, stop, restart, reload after a config change
- Reading a harness's output without attaching to its terminal
- **Spawning a new agent run from inside an existing one** (escalation)
- Diagnosing a scheduled harness that did not fire

## Talking to the daemon

Every verb goes over a Unix socket, `$XDG_RUNTIME_DIR/harness.sock`, falling back to `~/.local/state/harness/harness.sock` where `XDG_RUNTIME_DIR` is unset (macOS). It is mode `0600` and owned by the user running the daemon.

**This works from inside a supervised agent.** The daemon spawns children with the full environment, so a harness-managed agent inherits the same socket path and runs as the same UID — `0600` is not a barrier to itself. A `bash` tool call to `harness list` from inside a Crush or Claude Code session just works.

Override with `--socket PATH` when talking to a non-default daemon.

## Inspecting

```bash
harness list                      # every harness + state (the default verb)
harness --json list               # same, machine-readable — prefer this in scripts
harness describe <name>           # one harness in full: model, schedule, next run
harness logs <name> --lines 100   # log tail without attaching
harness doctor                    # config + daemon + harness health checks
```

`--json` is a **global** flag and goes before the verb. `list` returns an array of objects with `name`, `state`, `enabled`, `restart_count`, `last_exit_code`, `flapping`, `pid`, `adapter`, `backend`, `workdir`, `description`.

Parse `--json`; never scrape the table. The table wraps long descriptions across lines and will not survive `grep`.

## Lifecycle

```bash
harness start <name>      # start (and enable) it
harness stop <name>       # stop (and disable) it
harness restart <name>    # restart, clearing a failed latch
harness reload            # re-read harness definitions + harness.d drop-ins
```

`harness reload` re-reads harness definitions and drop-ins. It does **not** re-read the `[server]` block — changing the SSH listener or its port needs a full daemon restart.

## Spawning a run (and escalating)

```bash
harness run ARG...                        # throwaway harness, random name, then attach
harness run --detach ARG...               # skip the attach, leave it running
harness run --kind claude-code --workdir ~/src/foo "do the thing"
```

`--kind` takes `crush`, `claude` / `claude-code`, `codex`, or `generic`.

**It auto-detaches for non-interactive callers.** The interactive check requires a TTY on *both* stdout and stdin, and `--json` also skips the attach. An agent's `bash` tool has neither, so `harness run ...` from inside an agent backgrounds itself correctly — `--detach` is belt-and-braces there, not required.

### Escalation is fire-and-forget

There is **no result channel**. A spawned run cannot return anything to its
parent: the parent gets a name, not an answer.

So the workable pattern is *hand off*, not *call*:

> A cheap model triages, decides an item is beyond it, spawns a run scoped to
> that one item, records in its own summary that it escalated and why, and moves
> on. The escalated run reports through its own channel (its Signal summary, a
> PR it opens) — separately, later.

Do **not** write an escalation that waits for, polls for, or depends on the
child's answer. Give the child everything it needs in its prompt, because that
prompt is the entire handoff.

```bash
harness run --detach --kind crush \
  "Investigate <specific thing>, in <repo>. Context: <what was already
   established>. Open a PR if a fix is warranted."
```

Scope the child prompt tightly. An escalation whose prompt is "look into it"
spends a full context rediscovering what the parent already knew.

### You cannot choose the model for a scratchpad run

`harness run` has **no `--model` flag** — the whole surface is `--workdir`,
`--kind`, `--name`, `--detach` (`cmd/harness/run.go`). Passing `--model`
fails with `unknown flag: --model`, and putting it after the prompt does not
help either: the flag is passed through to the adapter, and the run still
exits non-zero.

A scratchpad therefore runs on whatever model its adapter defaults to. **A
"escalate to a stronger model" instruction written as a `harness run` command
does not work**, however plausible it looks — it was shipped once and had to be
retracted.

To reach a *specific* model, the harness has to be **declared** in config with
its own `model =` and started by name:

```bash
harness start <name>          # uses the model pinned in its harness.d entry
```

The trade-off is that a declared harness has a fixed `prompt`, so it cannot
carry a per-incident handoff. Until `harness run` grows a `--model` flag, pick
one: a dynamic prompt on the default model, or a fixed prompt on a chosen
model. You cannot have both.

## Gotchas that cost real time

**`harness stop` does NOT disarm a schedule.** For a scheduled harness, `enabled` governs the daemon lifecycle only — the cron still fires. A stopped-but-scheduled harness shows `state ○ stopped`, `enabled no`, *and* a live `next run`. To actually stop it firing, remove or comment the `schedule` key and `harness reload`. Check with `harness describe <name>` and confirm **no `next run` line**, not just that the state says stopped.

**A `schedule` is evaluated in the host's LOCAL time.** The same drop-in on machines in two timezones fires at two different absolute times — that is one full run per machine, not one run. Gate a scheduled harness to a single host.

**Provider/model resolution needs the secrets in the environment.** `crush models` (and any `--model provider/x` pin) only lists providers whose API key resolves. In a non-interactive shell with no secrets sourced, most providers vanish and a perfectly valid model id reads as "not found". Source the environment first — a missing model is usually a missing key, not a missing model.

**A model that answers `curl` may still fail every agent call.** Tool calling is separately enabled server-side. A self-hosted vLLM without `--enable-auto-tool-choice` and a matching `--tool-call-parser` returns fine for plain completions and fails at stream-open for anything with `tool_choice: "auto"` — which is every agent request. Test a new model with a real tool-using run, never a bare completion.

**`--json` before the verb.** `harness list --json` is not the same thing and will not give you JSON.

## What does not exist

No MCP server, no HTTP/REST API. `internal/facade` and the `mcp_allow` config key exist in the source but are unwired — `mcp_allow` parses and does nothing, and the facade is imported by nothing. ADR-0010 proposes an MCP surface; it is `status: proposed`.

The `[server]` block is a Charmbracelet Wish **SSH** listener that hosts the interactive TUI in-process. It is for humans on other machines, not for programmatic control — driving a Bubble Tea alt-screen over a PTY is not an API. Use the Unix socket.

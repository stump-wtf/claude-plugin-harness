---
name: harness-control
description: Operate a RUNNING harness daemon from the command line — inspect state, start/stop/restart a harness, read logs and per-run job logs, list and trigger scheduled jobs, spawn a throwaway agent run, and escalate work from one agent to another. Use when a request is about running harnesses rather than configuring them ("what agents are running", "restart the sweep", "run the nightly job now", "why did my scheduled harness not fire", "what did run 3 do", "kick off an agent to do X", "escalate this to a bigger model"). For authoring harness.toml itself, use harness-config instead.
---

# Harness Control

Operating a live [harness](https://stump-wtf.github.io/harness/) daemon. This is the runtime
half; `harness-config` is the authoring half.

The CLI **is** the supported programmatic surface (ADR-0002), and `--json` is a first-class
contract on it. There is no MCP server and no HTTP API — do not go looking for one.

## Flag placement, or nothing works

- **Global flags go BEFORE the verb**: `--socket`, `--config`, `--json`.
  `harness list --json` is not the same thing and will not give you JSON.
- **Verb flags go AFTER the verb**: `--lines`, `--follow`, `--run`, `--limit`, `--wait`,
  `--all`, `--ro`, `--detach`. `harness --lines 3 logs demo` is a parse error.

## Talking to the daemon

Every verb goes over a Unix socket, `$XDG_RUNTIME_DIR/harness.sock`, falling back to
`~/.local/state/harness/harness.sock` where `XDG_RUNTIME_DIR` is unset (macOS). It is mode
`0600` and owned by the user running the daemon.

**This works from inside a supervised agent.** The daemon spawns children with the full
environment, so a harness-managed agent inherits the same socket and UID — `0600` is not a
barrier to itself. A `bash` call to `harness list` inside a Crush or Claude Code session works.

Override with `--socket PATH` when talking to a non-default daemon.

## Inspecting

```bash
harness list                      # every harness + state (the default verb)
harness --json list               # machine-readable — prefer this in scripts
harness ps                        # inside a project: only that project's harnesses
harness describe <name>           # one harness in full: model, schedule, next run
harness doctor                    # config + daemon + harness health checks
harness profiles                  # list profiles (active one flagged)
```

`list --json` returns objects with `name`, `state`, `enabled`, `restart_count`,
`last_exit_code`, `flapping`, `pid`, `adapter`, `backend`, `workdir`, `description`.

A harness frozen at an interactive prompt shows a **waiting marker** in `list` and
`describe` (v0.11.0): `● running ⏸ waiting for input (y/n prompt) · screen idle 4m12s`.
`harness capture <name>` renders the screen it is stuck on, so you can see the dialog
without attaching.

Parse `--json`; never scrape the table — it wraps long descriptions and will not survive `grep`.

**Inside a project, a bare NAME resolves to `<project>/NAME`** for
describe/logs/start/stop/restart/attach/rm; run the verb outside the project to address a
global harness. The **job verbs are never project-scoped** — scheduled harnesses are global.

## Lifecycle

```bash
harness start <name>      # start (and enable) it       (--all for every harness)
harness stop <name>       # stop (and disable) it
harness restart <name>    # restart, clearing a failed latch
harness reload            # re-read harness definitions + harness.d drop-ins
harness rm <name>         # stop + deregister one registered harness
harness up / down         # project-scoped: bring the enclosing project up / down
```

**Since v0.11.0, `harness stop` suppresses the schedule.** The process stops AND the cron
stops firing until an explicit `harness start` re-arms it (`harness trigger` runs once
without re-arming). `describe` reads `next run: suppressed by harness stop`. The pause
survives a daemon restart. (Before v0.11.0 the cron kept firing over a stopped harness;
older notes saying otherwise are wrong.)

`harness reload` does **not** re-read the `[server]` block — changing the SSH listener or its
port needs a full daemon restart.

## Scheduled jobs, triggers and run history

```bash
harness jobs                      # every triggered harness: sources, next run, last run, failures
harness triggers                  # every [channel.*]/[webhook.*] source: state, last event, counters
harness runs <name>               # one harness's run history, newest first (--limit, default 20)
harness runs                      # every harness, last 24h (--since 7d, --outcome failed,..., --wide)
harness trigger <name>            # run it now — on_overlap applies, as for a real firing
harness trigger <name> --wait     # …stream its log and exit with its exit code
harness logs <name> --run 3       # what run 3 did (--raw for that run's own log)
```

- **`harness jobs` takes no arguments.** `harness jobs my-sweep` is an error.
- **`harness run` is NOT the job trigger.** It is the scratchpad verb (below). The manual-run
  verb is `trigger`, deliberately, so one verb never means two things.
- `trigger` reports `started`, `queued`, or `skipped` per the harness's `on_overlap`. A
  queued trigger has no run id yet; `--wait` polls for the run it produces.
- **`--wait` exit codes are not all 1**: `124` on timeout, `75` on skipped, otherwise the
  run's own exit code.
- Run outcomes you will see in `runs`: `success`, `failed`, `timed_out`, `skipped`,
  `replaced`, `missed`, `cancelled`, `interrupted`. A `missed` record covering several
  windows renders `missed ×4`. `interrupted` means the daemon died under that run.
- **`harness runs` without a name queries every harness at once** (v0.11.0) and works
  **offline** — it reads the run ledger's files directly when the daemon is down, showing a
  run it cannot classify as `running?`. `--wide` adds MODEL, TOKENS, COST and TODO columns;
  MODEL is the **served** model that did the most output tokens, folded from usage reports,
  not just the configured one. Full flag reference:
  https://stump-wtf.github.io/harness/usage/cli/#run-history-across-harnesses

## Reading logs — and a one-shot's RESULT line

```bash
harness logs <name>                    # agent activity, default 200 entries
harness logs <name> --lines 50         # a specific number
harness logs <name> --follow           # stream as it arrives
harness logs <name> --raw              # the durable log tail instead of activity
harness logs <name> --run N --raw      # run N's own log (the .stream.jsonl tail + run log)
```

By default `logs` renders **agent-trace activity** — lifecycle, tool calls, and marks, one
line each with detail clipped to 160 chars. `--raw` gives the durable log instead.

**The activity view never prints the durable log** (#328) — when nothing is attributable you
get notice lines naming `harness logs <name> --raw`, and no log. A `generic` harness differs:
it has no native transcript, so its source is not agent-trace and the client prints its
durable log directly. Check `harness --version` before trusting either half.

**A one-shot reports its own outcome by printing a RESULT line as its last output** — the
house sweeps print e.g. `SWEEP_RESULT: ok | reviewed=N | summary=LINK` or
`SWEEP_RESULT: blocked | REASON` (the exact prefix is the harness's own convention; see its
prompt). After a run ends, read it from the run's own log:

```bash
harness logs <name> --run N --raw | grep RESULT      # the durable log tail
harness trigger <name> --wait                        # or stream it live as the run goes
```

Run logs rotate closed and are stored zstd-compressed (`.log.zst`); `harness logs` reads
either form. By hand: `zstdgrep 'RESULT' ~/.local/state/harness/jobs/<name>/*.log*`.

`--run` cannot be combined with `--follow`; use `harness trigger <name> --wait` to follow a
run as it happens.

## Spawning a run (and escalating)

```bash
harness run ARG...                        # throwaway harness, random name, then attach
harness run --detach ARG...               # skip the attach, leave it running
harness run --kind claude-code --model claude-opus-5 --workdir ~/src/foo "do the thing"
```

Flags: `--workdir`, `--kind`, `--name`, `--model`, `--detach`. `--kind` takes `crush`,
`claude` / `claude-code`, `codex`, or `generic`; the first positional is dispatched as a kind
word if it matches one, otherwise the whole invocation runs via `sh -c` as `generic`.

**It auto-detaches for non-interactive callers.** The interactive check requires a TTY on
*both* stdout and stdin, and `--json` also skips the attach. An agent's `bash` tool has
neither, so `harness run ...` from inside an agent backgrounds itself correctly — `--detach`
is belt-and-braces there, not required.

### Scratchpads die with the daemon

A scratchpad exists only in the daemon's memory: **a daemon restart, a crash, or a redeploy
of the daemon (a `harness` package upgrade on the host) kills every scratchpad worker and
their work is gone** — they are never written to the daemon's state. Use a scratchpad for a
one-off session you are attached to right now. Anything that must survive a redeploy, run on
a clock, or fire on an event belongs in `harness.toml` instead: a resident harness, or a
prompt harness fired with `schedule`, `triggers` or `harness trigger` (see the
`harness-config` skill).

### Escalation is fire-and-forget

There is **no result channel**. A spawned run cannot return anything to its parent: the
parent gets a name, not an answer.

So the workable pattern is *hand off*, not *call*:

> A cheap model triages, decides an item is beyond it, spawns a run on a stronger model
> scoped to that one item, records in its own summary that it escalated and why, and moves
> on. The escalated run reports through its own channel (its Signal summary, a PR it opens) —
> separately, later.

Do **not** write an escalation that waits for, polls for, or depends on the child's answer.
Give the child everything it needs in its prompt, because that prompt is the entire handoff.

```bash
# from inside a sweep that has hit something it should not attempt itself
harness run --detach --kind crush --model <stronger-model> \
  "Investigate <specific thing>, in <repo>. Context: <what was already established>.
   Open a PR if a fix is warranted. Report via the usual Signal summary."
```

Scope the child prompt tightly. An escalation whose prompt is "look into it" spends a full
context rediscovering what the parent already knew.

## Gotchas that cost real time

**A bare `schedule` runs in the daemon's LOCAL time.** The same drop-in on machines in two
zones fires at two different absolute times — one full run per machine. Pin it with a
`CRON_TZ=<zone>` prefix (`schedule = "CRON_TZ=UTC 0 9 * * *"`), or gate the harness to one host.

**Provider/model resolution needs the secrets in the environment.** `crush models` (and any
`--model provider/x` pin) only lists providers whose API key resolves. In a non-interactive
shell with no secrets sourced, most providers vanish and a valid model id reads as "not
found". A missing model is usually a missing key.

**A model that answers `curl` may still fail every agent call.** Tool calling is separately
enabled server-side: a self-hosted vLLM without `--enable-auto-tool-choice` and a matching
`--tool-call-parser` serves plain completions fine and fails at stream-open for anything with
`tool_choice: "auto"` — every agent request. Test with a real tool-using run, not a bare one.

## Watching the merge train

The merge train (ADR-0032) runs inside the daemon and logs one structured line per
transition, each reading `mergetrain <event>`. Watch it from the host:

```bash
journalctl --user -u harness | grep mergetrain
```

The events (SPEC-0025 REQ-14):

| Event | Meaning |
|---|---|
| `started` / `stopped` | the driver started (mode, repos, base branch) or shut down |
| `queue` | the eligible PRs in merge order, whenever the queue changes |
| `stale` | a queued PR changed under the driver (head moved, closed); re-fetched |
| `would merge` / `would comment` | report mode: what it would have done |
| `merge refused` | the forge declined the pinned-head merge |
| `merged` | a train went green and was squash-merged |
| `verified` | the landed tree is the tested tree (byte check) |
| `commented` | the author-todo comment posted (one per head) |
| `tick failed` | a comment post failed; will retry |
| `bypass detected` | `main` moved without the train |
| `halted` | verification failed after a merge — an untested tree may be on `main`; do not restart before diagnosing |

## What does not exist

No MCP server, no HTTP/REST API, no `harness ls`, and no `enable`/`disable` verbs (the
protocol has the ops; nothing registers CLI verbs for them).

`internal/facade` defines only two read-class tools (`list_trajectories`, `get_trajectory`)
and **nothing serves them** — there is no MCP transport in the binary. The write trio appears
only in doc comments, so `mcp_allow` parses but grants nothing. ADR-0010 is `status: proposed`.

The `[server]` block is a Charmbracelet Wish **SSH** listener hosting the interactive TUI. It
is for humans on other machines, not programmatic control — driving a Bubble Tea alt-screen
over a PTY is not an API. Use the Unix socket.

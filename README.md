# claude-plugin-harness

[Claude Code](https://claude.com/claude-code) and [Crush](https://github.com/charmbracelet/crush)
plugin for configuring and operating [harness](https://stump-wtf.github.io/harness/) — the
agent supervisor TUI.

Mirror: https://github.com/stump-wtf/claude-plugin-harness

## Skills

- **harness-config** — author, edit, and review `harness.toml`. The required `harness`
  adapter enum, agent one-shots (`prompt` / `prompt_file`, `model`, `auto_accept`,
  `max_turns`, `quiet`), cron scheduling with `CRON_TZ=` time zones, the run controls
  (`catch_up`, `timeout`, `on_overlap`, `keep_runs`), profiles, and the `harness_d` drop-in
  directory — including the rule that decides whether a new harness goes in the main file or
  its own file. Detail lives in `skills/harness-config/references/schema.md`.
- **harness-control** — operate a *running* daemon: inspect state, lifecycle verbs, the
  scheduled-job verbs (`jobs`, `trigger --wait`, `runs`, `logs --run N`), reading agent
  activity vs the durable log, spawning a throwaway scratchpad run, and fire-and-forget
  escalation.

## Install

The plugin is public, so it installs from the GitHub mirror on any machine.

### Claude Code

```bash
claude plugin marketplace add stump-wtf/claude-plugin-harness
claude plugin install harness@claude-plugin-harness
```

Verify it loaded by asking Claude to add a scheduled harness and checking that it reaches for
`[harness.<name>]` with the required `harness = ` enum rather than the long-dead `cmd = `.

### Crush

Crush discovers skills by **path**, not by plugin install. Link or configure the `skills/`
directory itself — never the individual skills, or reads inside it lose their prompt-free
grant and get truncated:

```bash
git clone https://github.com/stump-wtf/claude-plugin-harness.git ~/src/claude-plugin-harness
ln -s ~/src/claude-plugin-harness/skills ~/.config/crush/skills-ext/harness
```

## What the skills do not do

- **They do not install or run harness.** See the
  [quickstart](https://stump-wtf.github.io/harness/usage/quickstart/) for that.
- **They grant nothing.** There is no MCP server and no HTTP API; the CLI over its Unix
  socket is the whole programmatic surface.

## Development

```bash
make check        # lint + test
make lint         # plugin metadata, skill frontmatter, and the two silent budgets
make test         # every ```toml example must parse
```

`make test` extracts every ```toml block from every `SKILL.md` **and every
`skills/*/references/*.md`** and validates it. When a `harness` binary is on `PATH` it uses
the real parser — the same one the daemon runs; otherwise it falls back to `tomllib` plus the
schema rules in `scripts/validate-examples.py`. **Install from `main`, not the released
tag** — `harness_d` and the run controls are unreleased:

```bash
go install gitea.stump.rocks/stump.wtf/harness/cmd/harness@main
```

Blocks that are fragments rather than standalone configs carry an annotation on the line
above the fence:

```markdown
<!-- validate: expect-fail -->   the block MUST be rejected (a WRONG example)
<!-- validate: skip reason -->   not a standalone config; a reason is required
<!-- validate: stub a,b -->      prepend minimal [harness.a]/[harness.b] tables
```

`make lint` additionally enforces what a harness applies silently: a description over 900
characters (or over 1024 once XML-escaped) drops the skill from the prompt with no
diagnostic, a body over 180 lines belongs partly in `references/`, and `user-invocable` on a
body containing fenced snippets mangles every one of them.

This tooling exists because the skill once shipped for months teaching `cmd = "crush"` after
upstream replaced `cmd` with the required `harness` enum — every example in it was a hard
parse error, and nothing noticed.

## License

MIT

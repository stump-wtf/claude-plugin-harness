# claude-plugin-harness

Claude Code and Crush plugin for configuring and using
[harness](https://gitea.stump.rocks/stump.wtf/harness) — the agent supervisor TUI.

## Skills

- **harness-config** — Author, edit, and review `harness.toml`. Covers the
  required `harness` adapter enum, agent one-shots (`prompt`, `model`,
  `auto_accept`, `max_turns`, `quiet`), cron scheduling, profiles, MCP facade
  scoping (`harvest_trajectory`, `mcp_allow`), and the `harness_d` drop-in
  directory — including the rule that decides whether a new harness goes in the
  main file or its own file.

## Installation

### Claude Code

```bash
claude plugin install https://gitea.stump.rocks/stump.wtf/claude-plugin-harness
```

### Crush

Add to your `crush.json` skills paths or clone into your skills directory.

## Development

```bash
make check        # lint + test
make lint         # plugin metadata + skill frontmatter
make test         # every ```toml example must parse
```

`make test` extracts every ```toml block from every `SKILL.md` and validates it.
When a `harness` binary is on `PATH` it uses the real parser — the same one the
daemon runs; otherwise it falls back to `tomllib` plus the schema rules in
`scripts/validate-examples.py`. **Install from `main`, not the released tag**:

```bash
go install gitea.stump.rocks/stump.wtf/harness/cmd/harness@main
```

Blocks that are fragments rather than standalone configs carry an annotation on
the line above the fence:

```markdown
<!-- validate: expect-fail -->   the block MUST be rejected (a WRONG example)
<!-- validate: skip reason -->   not a standalone config; a reason is required
<!-- validate: stub a,b -->      prepend minimal [harness.a]/[harness.b] tables
```

This exists because the skill once shipped for months teaching `cmd = "crush"`
after upstream replaced `cmd` with the required `harness` enum — every example
in it was a hard parse error.

## License

MIT

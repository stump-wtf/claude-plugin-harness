#!/usr/bin/env python3
"""
Structural Lint For The Plugin Metadata And Skills

Cheap checks for the things that make a plugin fail to load rather than fail to
work: malformed JSON, a skill with no YAML frontmatter (Claude Code cannot
discover it), a plugin name that disagrees with its marketplace entry.

@joestump-agent 08/20/2026 - Added after harness-config shipped with no
frontmatter at all, so nothing could trigger it.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors = []


def fail(msg):
    errors.append(msg)


def load_json(path):
    try:
        return json.loads(path.read_text())
    except Exception as exc:
        fail(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
        return None


plugin = load_json(ROOT / ".claude-plugin" / "plugin.json")
market = load_json(ROOT / ".claude-plugin" / "marketplace.json")

if plugin is not None:
    for key in ("name", "version", "description"):
        if not plugin.get(key):
            fail(f"plugin.json: missing required key {key!r}")

if plugin is not None and market is not None:
    names = {p.get("name") for p in market.get("plugins", [])}
    if plugin.get("name") not in names:
        fail(
            f"marketplace.json: no entry for plugin {plugin.get('name')!r} "
            f"(has {sorted(n for n in names if n)})"
        )

# The two budgets a harness enforces silently. A description past the hard cap once
# XML-escaped drops the skill from the prompt with no diagnostic — which is why the
# house cap is 900 and not 1024, and why escapable characters are counted: each costs
# six characters there and one here. The body cap is what keeps the always-loaded cost
# bounded; overflow belongs in references/, which is read only when needed.
DESC_CAP = 900
BODY_CAP = 180
ESCAPABLE = "&<>\"'"

skills = sorted(ROOT.glob("skills/*/SKILL.md"))
if not skills:
    fail("no skills/*/SKILL.md found")

for skill in skills:
    rel = skill.relative_to(ROOT)
    text = skill.read_text()
    if not text.startswith("---\n"):
        fail(f"{rel}: missing YAML frontmatter — the skill cannot be discovered")
        continue
    end = text.find("\n---\n", 4)
    if end == -1:
        fail(f"{rel}: frontmatter is not terminated by a '---' line")
        continue
    front = text[4:end]
    body = text[end + len("\n---\n"):]
    for key in ("name:", "description:"):
        if not any(line.startswith(key) for line in front.splitlines()):
            fail(f"{rel}: frontmatter is missing {key.rstrip(':')!r}")
    for line in front.splitlines():
        if line.startswith("name:"):
            declared = line.split(":", 1)[1].strip()
            if declared != skill.parent.name:
                fail(
                    f"{rel}: frontmatter name {declared!r} does not match "
                    f"directory {skill.parent.name!r}"
                )

    desc = re.search(r"^description:.*?(?=\n[a-zA-Z_-]+:|\Z)", front, re.S | re.M)
    if desc is not None:
        flat = " ".join(desc.group(0).split())[len("description: "):]
        escaped = len(flat) + sum(flat.count(c) for c in ESCAPABLE) * 5
        if len(flat) > DESC_CAP:
            fail(f"{rel}: description is {len(flat)} chars, over the {DESC_CAP} house cap")
        elif escaped > 1024:
            fail(
                f"{rel}: description is {len(flat)} chars but {escaped} once XML-escaped, "
                "over the 1024 hard cap — the skill would be dropped silently"
            )

    # Invoking a skill as a slash command runs its whole body through the prompt's HTML
    # escaper, mangling every quote, > and < in every snippet. A skill full of shell is
    # exactly the wrong thing to make user-invocable.
    if any(l.strip().startswith("user-invocable:") for l in front.splitlines()):
        if "```" in body:
            fail(f"{rel}: 'user-invocable' on a body containing fenced snippets mangles them")

    n = len(body.splitlines())
    if n > BODY_CAP:
        fail(f"{rel}: body is {n} lines, over the {BODY_CAP} cap — move detail to references/")

for msg in errors:
    print(f"FAIL {msg}")
print(f"{len(skills)} skill(s) checked, {len(errors)} failure(s)")
sys.exit(1 if errors else 0)

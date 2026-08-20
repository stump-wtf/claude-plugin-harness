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

for msg in errors:
    print(f"FAIL {msg}")
print(f"{len(skills)} skill(s) checked, {len(errors)} failure(s)")
sys.exit(1 if errors else 0)

#!/usr/bin/env python3
"""
Validate The TOML Examples Embedded In The Skills

Every ```toml block in a SKILL.md is config a model will copy verbatim, so a
block that no longer parses is a bug that ships. This extracts each block and
checks it: against the real `harness` binary when one is on PATH (authoritative
— it is the same parser the daemon runs), otherwise against tomllib plus the
subset of schema rules that have actually broken examples here before.

Blocks are annotated with an HTML comment on the line before the fence:

    <!-- validate: expect-fail -->   the block MUST be rejected (a WRONG example)
    <!-- validate: skip reason -->   not a standalone config; reason is required
    <!-- validate: stub a,b -->      prepend minimal [harness.a]/[harness.b] tables
                                     so a [profile.*] block can name real members

With no annotation the block must parse clean.

@joestump-agent 08/20/2026 - Written after every example in harness-config
SKILL.md turned out to be a hard parse error: `cmd` had been replaced by the
required `harness` enum upstream and nothing here noticed.
"""

import re
import subprocess
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- The schema rules, for the no-binary fallback -------------------------

ADAPTERS = {"crush", "claude-code", "codex", "generic"}
RESTARTS = {"no", "always", "unless-stopped", "on-failure"}
BACKENDS = {"native", "tmux"}
# Keys that are folded into the synthesized agent argv at spawn, so they are
# meaningless without a prompt and the parser rejects them without one.
REQUIRES_PROMPT = ("model", "auto_accept", "max_turns", "quiet", "schedule")
REMOVED = {
    "cmd": 'replaced by the required "harness" enum',
    "agent": 'renamed to "harness"',
}


def check_schema(doc):
    """Re-implement the rules that have bitten these examples. Returns errors."""
    errs = []
    tables = dict(doc.get("harness", {}))
    # Bare [name] tables are still accepted upstream; treat any other top-level
    # table that looks like a harness the same way.
    for key, val in doc.items():
        if key in ("harness", "profile", "daemon", "server"):
            continue
        if isinstance(val, dict):
            tables[key] = val

    for name, h in tables.items():
        if not isinstance(h, dict):
            continue
        for dead, why in REMOVED.items():
            if dead in h:
                errs.append(f'harness "{name}": "{dead}" was {why}')
        adapter = h.get("harness")
        if adapter is None:
            errs.append(f'harness "{name}": missing required key "harness"')
        elif adapter not in ADAPTERS:
            errs.append(f'harness "{name}": unknown harness kind {adapter!r}')
        prompt = h.get("prompt")
        if prompt and h.get("args"):
            errs.append(f'harness "{name}": "prompt" and "args" are mutually exclusive')
        for key in REQUIRES_PROMPT:
            if key in h and not prompt:
                errs.append(f'harness "{name}": "{key}" requires "prompt"')
        if h.get("restart") is not None and h["restart"] not in RESTARTS:
            errs.append(f'harness "{name}": invalid restart policy {h["restart"]!r}')
        if h.get("backend") is not None and h["backend"] not in BACKENDS:
            errs.append(f'harness "{name}": invalid backend {h["backend"]!r}')
        for key in ("restart_delay", "max_turns"):
            if isinstance(h.get(key), int) and h[key] < 0:
                errs.append(f'harness "{name}": "{key}" must not be negative')
        if isinstance(h.get("model"), str) and h["model"].split() != [h["model"]]:
            errs.append(f'harness "{name}": "model" must be a single token')
        if "/" in name:
            errs.append(f'harness "{name}": name must not contain "/"')
        if h.get("schedule") and h.get("enabled"):
            errs.append(f'harness "{name}": "schedule" and "enabled" are exclusive')
        if h.get("schedule") and h.get("restart") in ("always", "unless-stopped"):
            errs.append(f'harness "{name}": "schedule" needs restart no/on-failure')

    for pname, p in doc.get("profile", {}).items():
        for member in p.get("harnesses", []):
            if member not in tables:
                errs.append(f'profile "{pname}": unknown harness "{member}"')
            elif tables[member].get("schedule"):
                errs.append(f'profile "{pname}": member "{member}" is scheduled')
    return errs


# --- Validation back ends -------------------------------------------------


def validate_with_binary(binary, text):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "harness.toml"
        path.write_text(text)
        proc = subprocess.run(
            [binary, "doctor", "--config", str(path)],
            capture_output=True,
            text=True,
        )
        out = proc.stdout + proc.stderr
        # doctor reports every check; only the config row matters here, and a
        # missing daemon must not be mistaken for a bad config.
        for line in out.splitlines():
            if line.startswith("config") and " ok " in line:
                return []
        # doctor renders the detail in a wrapped, padded column; collect the
        # config row and its continuation lines, then squash the padding.
        detail, collecting = [], False
        for line in out.splitlines():
            if line.startswith("config"):
                collecting = True
                detail.append(line[len("config"):])
                continue
            if collecting:
                if not line.startswith(" ") or not line.strip():
                    break
                detail.append(line)
        joined = " ".join(" ".join(detail).split())
        for noise in ("error parse failed:", "error", "→ fix the TOML syntax and re-run `harness doctor`"):
            joined = joined.replace(noise, " ")
        # A binary with no daemon still reports config errors; anything else is
        # a hard failure worth surfacing verbatim.
        return [" ".join(joined.split()) or out.strip() or "config check did not pass"]


def validate_with_tomllib(text):
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - python < 3.11
        return ["python 3.11+ (tomllib) or the harness binary is required"]
    try:
        doc = tomllib.loads(text)
    except Exception as exc:
        return [f"TOML syntax: {exc}"]
    return check_schema(doc)


# --- Block extraction -----------------------------------------------------

DIRECTIVE = re.compile(r"<!--\s*validate:\s*(?P<body>[^>]*?)\s*-->")
FENCE = re.compile(r"^```toml\s*$")


def blocks(path):
    """Yield (line_no, directive, text) for every ```toml block in path."""
    lines = path.read_text().splitlines()
    pending = None
    i = 0
    while i < len(lines):
        line = lines[i]
        m = DIRECTIVE.search(line)
        if m:
            pending = m.group("body")
            i += 1
            continue
        if FENCE.match(line):
            start = i + 1
            j = start
            while j < len(lines) and lines[j].strip() != "```":
                j += 1
            yield start + 1, pending, "\n".join(lines[start:j]) + "\n"
            pending = None
            i = j + 1
            continue
        if line.strip():
            pending = None
        i += 1


STUB = '[harness.{name}]\nharness = "generic"\nargs = ["-c", "true"]\n'


def main():
    binary = shutil.which("harness")
    mode = f"harness binary ({binary})" if binary else "tomllib + schema rules"
    print(f"validating skill TOML examples via {mode}")

    failures = 0
    checked = 0
    for skill in sorted(ROOT.glob("skills/*/SKILL.md")):
        rel = skill.relative_to(ROOT)
        for line_no, directive, text in blocks(skill):
            label = f"{rel}:{line_no}"
            verb, _, rest = (directive or "").partition(" ")
            if verb == "skip":
                if not rest.strip():
                    print(f"FAIL {label}: 'validate: skip' requires a reason")
                    failures += 1
                continue
            if verb == "stub":
                text = "".join(
                    STUB.format(name=n.strip()) for n in rest.split(",") if n.strip()
                ) + text
            elif directive and verb != "expect-fail":
                print(f"FAIL {label}: unknown validate directive {directive!r}")
                failures += 1
                continue

            checked += 1
            errs = validate_with_binary(binary, text) if binary else validate_with_tomllib(text)

            if verb == "expect-fail":
                if not errs:
                    print(f"FAIL {label}: marked expect-fail but parsed clean")
                    failures += 1
            elif errs:
                print(f"FAIL {label}:")
                for e in errs:
                    print(f"       {e}")
                failures += 1

    print(f"{checked} block(s) checked, {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""Set memory.provider, memory.auto_inject and memory.auto_extract in a
config.yaml in place, keeping every other byte (comments included).

    python scripts/set_memory_mode.py aios/config/config.yaml \\
        --provider mem0 --kernel-memory on|off [--extract on|off]
        [--recency off|time|session] [--barrier-timeout-ms N] [--k N]
        [--budget N]

``--kernel-memory`` sets ``auto_inject`` and ``auto_extract`` together;
``--extract`` then sets ``auto_extract`` alone (benchmark v2 kernel runs
use ``--kernel-memory on --extract off``: a probe writes nothing,
docs/BENCHMARK_V2.md, Amendment 3).

``--recency`` also sets the block's ages (docs/BENCHMARK_V2.md,
"Recency"): ``off`` is ``block_recency: false`` with the default unit
``"time"``; ``time`` and ``session`` turn ages on in that unit. Without
it, the recency keys are left as they are. ``--barrier-timeout-ms``
sets ``memory.write_barrier.timeout_ms`` (benchmark v2 kernel runs use
60000, so a probe never runs without the previous one's conversation).
``--k`` and ``--budget`` set ``memory.max_injected_memories`` and
``memory.max_memory_tokens`` (benchmark v2 runs use 10 and 300).

Run drivers call it between runs, never during one.
"""
import argparse
import re

import yaml

# --recency: (memory.block_recency, memory.block_recency_unit).
RECENCY = {
    "off": (False, "time"),
    "time": (True, "time"),
    "session": (True, "session"),
}


def set_mode(text: str, provider: str, kernel_memory: bool) -> str:
    value = "true" if kernel_memory else "false"
    replacements = [
        (r'^(  provider: )"[^"]*"', rf'\g<1>"{provider}"'),
        (r"^(  auto_extract: )(true|false)( *)",
         lambda m: m.group(1) + value
         + " " * max(1, len(m.group(2)) + len(m.group(3)) - len(value))),
        (r"^(  auto_inject: )(true|false)( *)",
         lambda m: m.group(1) + value
         + " " * max(1, len(m.group(2)) + len(m.group(3)) - len(value))),
    ]
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, flags=re.M)
        if count != 1:
            raise SystemExit(f"expected one match for {pattern!r}, got {count}")
    memory = yaml.safe_load(text)["memory"]
    assert memory["provider"] == provider
    assert memory["auto_inject"] is kernel_memory
    assert memory["auto_extract"] is kernel_memory
    return text


def set_extract(text: str, extract: bool) -> str:
    """Set ``memory.auto_extract`` alone, matched exactly once, a
    trailing comment kept in its column."""
    text, count = re.subn(
        r"^(  auto_extract: )(true|false)([ \t]*)(#.*)?$",
        _keep_column("true" if extract else "false"), text, flags=re.M,
    )
    if count != 1:
        raise SystemExit(f"expected one auto_extract line, got {count}")
    assert yaml.safe_load(text)["memory"]["auto_extract"] is extract
    return text


def _keep_column(value: str):
    """A replacement that writes ``value`` and keeps a trailing comment
    in its column (at least one space before it)."""
    def replace(match: re.Match) -> str:
        head, old, gap, comment = match.groups()
        if comment is None:
            return head + value + gap
        return (
            head + value
            + " " * max(1, len(old) + len(gap) - len(value)) + comment
        )
    return replace


def set_recency(text: str, recency: str) -> str:
    """Set ``memory.block_recency`` and ``memory.block_recency_unit``
    for ``--recency`` (``RECENCY``), each line matched exactly once."""
    enabled, unit = RECENCY[recency]
    replacements = [
        (r"^(  block_recency: )(true|false)([ \t]*)(#.*)?$",
         _keep_column("true" if enabled else "false")),
        (r'^(  block_recency_unit: )("[^"\n]*")([ \t]*)(#.*)?$',
         _keep_column(f'"{unit}"')),
    ]
    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, flags=re.M)
        if count != 1:
            raise SystemExit(f"expected one match for {pattern!r}, got {count}")
    memory = yaml.safe_load(text)["memory"]
    assert memory["block_recency"] is enabled
    assert memory["block_recency_unit"] == unit
    return text


def set_barrier_timeout(text: str, timeout_ms: int) -> str:
    """Set ``memory.write_barrier.timeout_ms``, matched exactly once
    (the one ``timeout_ms`` key at four spaces of indent)."""
    if timeout_ms <= 0:
        raise SystemExit("--barrier-timeout-ms must be positive")
    text, count = re.subn(
        r"^(    timeout_ms: )(\d+)([ \t]*)(#.*)?$",
        _keep_column(str(timeout_ms)), text, flags=re.M,
    )
    if count != 1:
        raise SystemExit(f"expected one timeout_ms line, got {count}")
    memory = yaml.safe_load(text)["memory"]
    assert memory["write_barrier"]["timeout_ms"] == timeout_ms
    return text


def set_selection(text: str, k: int = None, budget: int = None) -> str:
    """Set ``memory.max_injected_memories`` (``k``) and / or
    ``memory.max_memory_tokens`` (``budget``), each matched exactly
    once at two spaces of indent, comments kept in their column."""
    for key, value in (("max_injected_memories", k),
                       ("max_memory_tokens", budget)):
        if value is None:
            continue
        if value <= 0:
            raise SystemExit(f"{key} must be positive")
        text, count = re.subn(
            rf"^(  {key}: )(\d+)([ \t]*)(#.*)?$", _keep_column(str(value)),
            text, flags=re.M,
        )
        if count != 1:
            raise SystemExit(f"expected one {key} line, got {count}")
        assert yaml.safe_load(text)["memory"][key] == value
    return text


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--kernel-memory", choices=["on", "off"],
                        required=True)
    parser.add_argument("--extract", choices=["on", "off"])
    parser.add_argument("--recency", choices=sorted(RECENCY))
    parser.add_argument("--barrier-timeout-ms", type=int)
    parser.add_argument("--k", type=int)
    parser.add_argument("--budget", type=int)
    args = parser.parse_args(argv)
    with open(args.config) as handle:
        text = handle.read()
    text = set_mode(text, args.provider, args.kernel_memory == "on")
    if args.extract:
        text = set_extract(text, args.extract == "on")
    if args.recency:
        text = set_recency(text, args.recency)
    if args.barrier_timeout_ms is not None:
        text = set_barrier_timeout(text, args.barrier_timeout_ms)
    text = set_selection(text, args.k, args.budget)
    with open(args.config, "w") as handle:
        handle.write(text)


if __name__ == "__main__":
    main()

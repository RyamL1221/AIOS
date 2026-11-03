"""Set memory.provider, memory.auto_inject and memory.auto_extract in a
config.yaml in place, keeping every other byte (comments included).

    python scripts/set_memory_mode.py aios/config/config.yaml \\
        --provider mem0 --kernel-memory on|off

Run drivers call it between runs, never during one.
"""
import argparse
import re

import yaml


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config")
    parser.add_argument("--provider", required=True)
    parser.add_argument("--kernel-memory", choices=["on", "off"],
                        required=True)
    args = parser.parse_args()
    with open(args.config) as handle:
        text = handle.read()
    text = set_mode(text, args.provider, args.kernel_memory == "on")
    with open(args.config, "w") as handle:
        handle.write(text)


if __name__ == "__main__":
    main()

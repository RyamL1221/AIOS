"""``scripts/set_memory_mode.py --recency`` (benchmark v2,
docs/BENCHMARK_V2.md, "Recency"): it sets ``memory.block_recency`` and
``memory.block_recency_unit`` in place, keeping every other byte;
without the flag the file is written as before the flag existed.
"""
from pathlib import Path

import pytest
import yaml

from scripts.set_memory_mode import RECENCY, main, set_mode, set_recency

ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = ROOT / "aios" / "config" / "config.yaml.example"
MODE_KEYS = ("  provider:", "  auto_extract:", "  auto_inject:")
RECENCY_KEYS = ("  block_recency:", "  block_recency_unit:")


def changed_lines(before: str, after: str) -> list:
    old, new = before.split("\n"), after.split("\n")
    assert len(old) == len(new)
    return [a for a, b in zip(old, new) if a != b]


def run(tmp_path, *flags) -> str:
    config = tmp_path / "config.yaml"
    config.write_text(EXAMPLE.read_text())
    main([str(config), "--provider", "mem0", "--kernel-memory", "on",
          *flags])
    return config.read_text()


def test_the_config_files_carry_the_unit():
    memory = yaml.safe_load(EXAMPLE.read_text())["memory"]
    assert (memory["block_recency"], memory["block_recency_unit"]) == (
        False, "time",
    )


def test_without_recency_only_the_mode_keys_change(tmp_path):
    original = EXAMPLE.read_text()
    written = run(tmp_path)
    assert written == set_mode(original, "mem0", True)
    assert changed_lines(original, written)
    assert all(
        line.startswith(MODE_KEYS)
        for line in changed_lines(original, written)
    )


@pytest.mark.parametrize("recency", ["off", "time", "session"])
def test_recency_sets_both_keys_and_keeps_the_rest(tmp_path, recency):
    original = EXAMPLE.read_text()
    written = run(tmp_path, "--recency", recency)
    memory = yaml.safe_load(written)["memory"]
    assert (memory["block_recency"], memory["block_recency_unit"]) == (
        RECENCY[recency]
    )
    assert all(
        line.startswith(MODE_KEYS + RECENCY_KEYS)
        for line in changed_lines(original, written)
    )


def recency_lines(text: str) -> dict:
    return {
        line.split(":")[0]: line for line in text.split("\n")
        if line.startswith(RECENCY_KEYS)
    }


def test_recency_keeps_the_comments():
    original = EXAMPLE.read_text()
    before = recency_lines(original)
    for recency in RECENCY:
        text = set_recency(original, recency)
        after = recency_lines(text)
        assert set(changed_lines(original, text)) <= set(before.values())
        # block_recency's comment keeps its column for either value.
        flag = "  block_recency"
        assert after[flag].index("#") == before[flag].index("#")
        # The unit's comment keeps its column where the value fits, and
        # follows a longer value after one space.
        unit, old = after["  block_recency_unit"], before[
            "  block_recency_unit"
        ]
        assert unit[unit.index("#"):] == old[old.index("#"):]
        assert '"time"   #' in unit or '"session" #' in unit
        assert set_recency(text, recency) == text  # idempotent
    # The example ships the default, recency off in the time unit.
    assert set_recency(original, "off") == original


def test_recency_refuses_a_config_without_the_unit_key():
    lines = [
        line for line in EXAMPLE.read_text().split("\n")
        if not line.startswith("  block_recency_unit:")
    ]
    with pytest.raises(SystemExit):
        set_recency("\n".join(lines), "session")


def test_barrier_timeout_sets_only_that_line(tmp_path):
    """Benchmark v2 kernel runs wait up to 60 s for the previous probe's
    conversation write (docs/BENCHMARK_V2.md, "Write barrier")."""
    original = EXAMPLE.read_text()
    config = tmp_path / "config.yaml"
    config.write_text(original)
    main([str(config), "--provider", "in-house", "--kernel-memory", "on",
          "--barrier-timeout-ms", "60000"])
    text = config.read_text()
    memory = yaml.safe_load(text)["memory"]
    assert memory["write_barrier"]["timeout_ms"] == 60000
    changed = [(a, b) for a, b in zip(original.split("\n"), text.split("\n"))
               if a != b]
    assert all("timeout_ms" in a or "auto_" in a or "provider" in a
               for a, _ in changed)
    assert [b for _, b in changed if "timeout_ms" in b] == [
        "    timeout_ms: 60000    # max wait per retrieval"]
    with pytest.raises(SystemExit):
        main([str(config), "--provider", "in-house", "--kernel-memory",
              "on", "--barrier-timeout-ms", "0"])


def test_k_and_budget_set_their_lines_only(tmp_path):
    """Benchmark v2 sets k 10 and a 300-token budget explicitly
    (docs/BENCHMARK_V2.md, "Loci and backends", Amendment 3)."""
    original = EXAMPLE.read_text()
    config = tmp_path / "config.yaml"
    config.write_text(original)
    main([str(config), "--provider", "in-house", "--kernel-memory", "on",
          "--k", "10", "--budget", "300"])
    text = config.read_text()
    memory = yaml.safe_load(text)["memory"]
    assert (memory["max_injected_memories"], memory["max_memory_tokens"]) \
        == (10, 300)
    changed = [b for a, b in zip(original.split("\n"), text.split("\n"))
               if a != b and "max_" in a]
    assert changed == [
        "  max_injected_memories: 10    # Max memories to inject per LLM call",
        "  max_memory_tokens: 300       # Token budget for injected memory block",
    ]
    # Without the flags the selection keys are untouched.
    config.write_text(original)
    main([str(config), "--provider", "in-house", "--kernel-memory", "on"])
    assert yaml.safe_load(config.read_text())["memory"][
        "max_memory_tokens"] == 1500


def test_extract_sets_auto_extract_alone(tmp_path):
    """Benchmark v2 kernel runs inject but do not extract: a probe
    writes nothing (docs/BENCHMARK_V2.md, Amendment 3)."""
    original = EXAMPLE.read_text()
    written = run(tmp_path, "--extract", "off")
    memory = yaml.safe_load(written)["memory"]
    assert (memory["auto_inject"], memory["auto_extract"]) == (True, False)
    assert all(line.startswith(MODE_KEYS)
               for line in changed_lines(original, written))
    assert yaml.safe_load(run(tmp_path, "--extract", "on"))["memory"][
        "auto_extract"] is True
    # Without the flag --kernel-memory sets both, as before.
    assert yaml.safe_load(run(tmp_path))["memory"]["auto_extract"] is True

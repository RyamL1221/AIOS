"""The shared memory block renderer (NeurIPS Subtask 9d).

The default ``compact`` block is one header line and a bullet per
memory: no delimiters, no instruction line, no per-line timestamp. The
pre-9d kernel block stays available as ``legacy`` behind
``memory.block_format``; ``memory.block_recency`` adds a relative age.
"""
from datetime import datetime
from unittest.mock import patch

import pytest

from aios.memory.manager import MemoryManager
from aios.memory.pipeline import MemoryPipeline, PipelineSettings
from aios.memory.pipeline.formatter import (
    COMPACT_HEADER,
    Formatter,
    block_contents,
    format_block,
    is_memory_block,
    relative_age,
)
from aios.memory.providers.in_house import InHouseProvider

ROWS = [
    {"memory_id": "p", "content": "My name is Ada.", "score": 0.9,
     "timestamp": "202611041200",
     "metadata": {"memory_type": "profile", "owner_agent": "profile_agent"}},
    {"memory_id": "t", "content": "I am porting the parser.", "score": 0.8,
     "timestamp": "202611051130",
     "metadata": {"memory_type": "task_context", "owner_agent": "task_agent"}},
]
NOW = datetime(2026, 11, 5, 12, 0)


def test_compact_block_is_a_header_and_bullets():
    assert format_block(ROWS) == (
        "Known about this user:\n"
        "- My name is Ada.\n"
        "- I am porting the parser."
    )
    assert COMPACT_HEADER == "Known about this user:"


def test_compact_block_has_no_timestamp_footer_or_instruction():
    text = format_block(ROWS, "compact")
    assert "202611" not in text
    assert "MEMORY CONTEXT" not in text
    assert "personalize" not in text
    assert not text.endswith("\n")


def test_legacy_block_is_the_pre_9d_kernel_block():
    assert format_block(ROWS, "legacy") == (
        "===== MEMORY CONTEXT =====\n"
        "The following are relevant memories from prior interactions "
        "with this user. Use them to personalize your response:\n"
        "\n"
        "- [202611041200] My name is Ada.\n"
        "- [202611051130] I am porting the parser.\n"
        "\n"
        "===== END MEMORY CONTEXT ====="
    )


def test_unknown_format_is_rejected():
    with pytest.raises(ValueError):
        format_block(ROWS, "fancy")
    with pytest.raises(ValueError):
        Formatter(100, "fancy")
    with pytest.raises(ValueError):
        PipelineSettings(block_format="fancy")


@pytest.mark.parametrize("minutes, expected", [
    (0, "just now"), (1, "1 minute ago"), (59, "59 minutes ago"),
    (60, "1 hour ago"), (150, "2 hours ago"), (1440, "1 day ago"),
    (3 * 1440 + 5, "3 days ago"),
])
def test_relative_age(minutes, expected):
    then = datetime.fromtimestamp(NOW.timestamp() - minutes * 60)
    assert relative_age(then.strftime("%Y%m%d%H%M"), NOW) == expected


def test_relative_age_of_an_unparseable_timestamp_is_none():
    assert relative_age("unknown", NOW) is None
    assert relative_age(None, NOW) is None


def test_recency_mode_adds_an_age_per_bullet_and_is_off_by_default():
    assert format_block(ROWS, recency=True, now=NOW) == (
        "Known about this user:\n"
        "- My name is Ada. (1 day ago)\n"
        "- I am porting the parser. (30 minutes ago)"
    )
    assert "ago" not in format_block(ROWS)
    assert PipelineSettings().block_recency is False
    row = dict(ROWS[0], timestamp="unknown")
    assert format_block([row], recency=True, now=NOW).endswith("Ada.")


def test_settings_read_and_report_the_block_format():
    settings = PipelineSettings.from_memory_config({})
    assert (settings.block_format, settings.block_recency) == (
        "compact", False,
    )
    legacy = PipelineSettings.from_memory_config(
        {"block_format": "legacy", "block_recency": True}
    )
    assert legacy.as_dict()["block_format"] == "legacy"
    assert legacy.as_dict()["block_recency"] is True
    # A replicated agent copies the kernel's report.
    assert PipelineSettings.from_memory_config(legacy.as_dict()) == legacy


def test_pipeline_builds_the_configured_format():
    store = InHouseProvider()
    store.initialize({})
    for block_format in ("compact", "legacy"):
        pipeline = MemoryPipeline(store, PipelineSettings(
            max_memory_tokens=1000, block_format=block_format,
        ))
        text, diagnostics = pipeline.build_block(ROWS)
        assert text == format_block(ROWS, block_format)
        assert diagnostics["block_format"] == block_format
        assert diagnostics["block_recency"] is False


def _manager(memory_config):
    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = memory_config
        config.get_storage_config.return_value = {}
        return MemoryManager()


def test_kernel_defaults_to_compact_and_honors_the_legacy_flag():
    base = {"provider": "in-memory"}
    assert _manager(base).pipeline_settings().block_format == "compact"
    legacy = _manager(dict(base, block_format="legacy"))
    assert legacy.pipeline_settings().block_format == "legacy"
    with pytest.raises(ValueError):
        _manager(dict(base, block_format="fancy"))


def test_block_parsing_helpers_read_both_formats():
    for block_format in ("compact", "legacy"):
        text = format_block(ROWS, block_format)
        assert is_memory_block(text)
        assert block_contents(text) == [
            "My name is Ada.", "I am porting the parser.",
        ]
    assert not is_memory_block("You are a helpful assistant.")
    assert block_contents("You are a helpful assistant.") == []

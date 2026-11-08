"""Session ages in the memory block (benchmark v2, docs/BENCHMARK_V2.md,
"Recency").

With ``memory.block_recency`` on and ``memory.block_recency_unit:
session``, each bullet ends with its age in sessions: the caller's
current session (``LLMQuery.session``) minus the row's
``metadata.session``. The kernel and a direct library call print the
same block, the conversation turn the kernel stores carries the
session, and the default unit, ``time``, prints the wall-clock ages as
before.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from cerebrum.llm.apis import LLMQuery
from cerebrum.memory.apis import MemoryQuery

from aios.memory.context_injector import ContextInjector
from aios.memory.conversation_extractor import ConversationExtractor
from aios.memory.manager import MemoryManager
from aios.memory.pipeline import (
    PROVENANCE_FIELDS,
    RECENCY_UNITS,
    TYPE_ORDER,
    MemoryPipeline,
    PipelineSettings,
    conversation_note,
    conversation_request,
    session_age,
)
from aios.memory.pipeline.formatter import (
    Formatter,
    estimate_tokens,
    format_block,
)
from aios.syscall.memory import MemorySyscall

NOW = datetime(2026, 11, 5, 12, 0)
USER = "alice"
AGENT = "assistant_agent"


def row(memory_id, content, session=None, memory_type="profile",
        owner="profile_agent", score=0.5, timestamp="202611041200",
        **metadata):
    """One selected candidate, as the selector hands it on."""
    meta = {"memory_type": memory_type, "owner_agent": owner, **metadata}
    if session is not None:
        meta["session"] = session
    return {
        "memory_id": memory_id, "content": content, "score": score,
        "timestamp": timestamp, "metadata": meta,
    }


ROWS = [
    row("a", "I live in Tallinn.", session=1),
    row("b", "We moved the team sync to the Birch room.", session=6),
    row("c", "User: where is the sync?\nAssistant: Birch.", session=7,
        memory_type="conversation", owner=AGENT),
    row("d", "No session on this one."),
]


def session_block(rows, block_format="compact", current_session=7):
    return format_block(
        rows, block_format, recency=True, recency_unit="session",
        current_session=current_session,
    )


@pytest.mark.parametrize("row_session, current, expected", [
    (7, 7, "this session"),
    (6, 7, "1 session ago"),
    (5, 7, "2 sessions ago"),
    (1, 7, "6 sessions ago"),
])
def test_session_age_wording(row_session, current, expected):
    assert session_age(row_session, current) == expected


@pytest.mark.parametrize("row_session, current", [
    (None, 7), ("3", 7), (3.0, 7), (True, 7),
    (3, None), (3, "7"),
    (8, 7),  # a row from after the current session
])
def test_no_session_age_without_integer_sessions_or_for_a_later_row(
    row_session, current,
):
    assert session_age(row_session, current) is None


def test_session_recency_compact_block():
    assert session_block(ROWS) == (
        "Known about this user:\n"
        "- I live in Tallinn. (6 sessions ago)\n"
        "- We moved the team sync to the Birch room. (1 session ago)\n"
        "- User: where is the sync?\nAssistant: Birch. (this session)\n"
        "- No session on this one."
    )


def test_session_recency_legacy_block():
    text = session_block(ROWS[:2], "legacy")
    assert "- [202611041200] I live in Tallinn. (6 sessions ago)" in text
    assert text.endswith("===== END MEMORY CONTEXT =====")


def test_no_session_ages_without_a_current_session_or_with_recency_off():
    plain = format_block(ROWS)
    assert session_block(ROWS, current_session=None) == plain
    assert format_block(
        ROWS, recency=False, recency_unit="session", current_session=7,
    ) == plain
    assert "ago" not in plain and "this session" not in plain


def test_time_unit_is_unchanged_and_ignores_the_session():
    rows = [
        row("p", "My name is Ada.", session=2, timestamp="202611041200"),
        row("t", "I am porting the parser.", session=3,
            timestamp="202611051130"),
    ]
    expected = (
        "Known about this user:\n"
        "- My name is Ada. (1 day ago)\n"
        "- I am porting the parser. (30 minutes ago)"
    )
    assert format_block(rows, recency=True, now=NOW) == expected
    assert format_block(
        rows, recency=True, now=NOW, recency_unit="time", current_session=7,
    ) == expected
    formatter = Formatter(1000, recency=True, now=NOW, current_session=7)
    assert formatter.recency_unit == "time"
    assert formatter.render(rows) == expected


def test_unknown_recency_unit_is_rejected():
    assert RECENCY_UNITS == ("time", "session")
    with pytest.raises(ValueError):
        format_block(ROWS, recency_unit="days")
    with pytest.raises(ValueError):
        Formatter(100, recency_unit="days")
    with pytest.raises(ValueError):
        PipelineSettings(block_recency_unit="days")
    with pytest.raises(ValueError):
        PipelineSettings.from_memory_config({"block_recency_unit": None})


def test_settings_read_and_report_the_recency_unit():
    assert PipelineSettings().block_recency_unit == "time"
    assert PipelineSettings.from_memory_config({}).block_recency_unit == (
        "time"
    )
    settings = PipelineSettings.from_memory_config(
        {"block_recency": True, "block_recency_unit": "session"}
    )
    assert settings.as_dict()["block_recency_unit"] == "session"
    # A replicated agent copies the kernel's report.
    assert PipelineSettings.from_memory_config(settings.as_dict()) == (
        settings
    )
    # A report from a kernel that predates the key reads as the default.
    report = settings.as_dict()
    del report["block_recency_unit"]
    assert PipelineSettings.from_memory_config(report).block_recency_unit \
        == "time"


def _manager(memory_config):
    with patch("aios.memory.manager.global_config") as config:
        config.get_memory_config.return_value = memory_config
        config.get_storage_config.return_value = {}
        return MemoryManager()


def test_kernel_reports_the_recency_unit_at_memory_config():
    base = {"provider": "in-memory"}
    assert _manager(base).pipeline_settings().block_recency_unit == "time"
    manager = _manager(
        dict(base, block_recency=True, block_recency_unit="session")
    )
    assert manager.block_recency_unit == "session"
    # /memory/config's "pipeline" is pipeline_settings().as_dict().
    report = manager.pipeline_settings().as_dict()
    assert (report["block_recency"], report["block_recency_unit"]) == (
        True, "session",
    )
    assert MemoryManager.__new__(MemoryManager).pipeline_settings() \
        .block_recency_unit == "time"
    with pytest.raises(ValueError):
        _manager(dict(base, block_recency_unit="days"))


def test_budget_counts_the_session_ages():
    rows = ROWS[:2]
    without_ages = estimate_tokens(format_block(rows))
    assert estimate_tokens(session_block(rows)) > without_ages
    formatter = Formatter(
        without_ages, recency=True, recency_unit="session",
        current_session=7,
    )
    _, diagnostics = formatter.build(rows)
    assert diagnostics["after_budget"] == 1


def test_build_reports_the_unit_the_session_and_each_rows_text():
    rows = [
        row("p", '{"name": "Ada"}', session=1, provenance_event="u0-e1",
            provenance_agent="profile_agent", provenance_user=USER,
            fact_key="base_profile"),
        row("t", "I am porting the parser.", session=6,
            memory_type="task_context"),
    ]
    text, diagnostics = Formatter(
        1000, recency=True, recency_unit="session", current_session=7,
    ).build(rows)
    assert diagnostics["block_recency"] is True
    assert diagnostics["block_recency_unit"] == "session"
    assert diagnostics["session"] == 7
    assert PROVENANCE_FIELDS == (
        "provenance_agent", "provenance_user", "provenance_event",
    )
    profile, task = diagnostics["injected_memories"]
    assert profile["provenance_event"] == "u0-e1"
    assert task["provenance_event"] is None
    # The fact and the session each row states (benchmark v2).
    assert (profile["fact_key"], profile["session"]) == ("base_profile", 1)
    assert (task["fact_key"], task["session"]) == (None, 6)
    # The text as printed, formatted, without the age.
    assert profile["content"] != '{"name": "Ada"}'
    assert text.split("\n")[1:] == [
        f"- {profile['content']} (6 sessions ago)",
        f"- {task['content']} (1 session ago)",
    ]
    _, plain = Formatter(1000).build(rows)
    assert (plain["block_recency_unit"], plain["session"]) == ("time", None)


def test_calendar_prints_between_task_context_and_conversation():
    assert TYPE_ORDER == (
        "profile", "task_context", "calendar", "conversation",
    )
    rows = [
        row("c", "chat", memory_type="conversation", score=0.9),
        row("k", "Team sync is in the Birch room.", memory_type="calendar",
            owner="calendar_agent", score=0.8),
        row("x", "other", memory_type="", score=0.7),
        row("t", "task", memory_type="task_context", score=0.6),
        row("p", "profile", score=0.1),
    ]
    _, diagnostics = Formatter(10_000).build(rows)
    assert [m["memory_id"] for m in diagnostics["injected_memories"]] == [
        "p", "t", "k", "c", "x",
    ]


# --- the kernel and the library print the same block -----------------

KERNEL_CONFIG = {
    "provider": "in-memory",
    "relevance_threshold": 0.0,
    "max_injected_memories": 10,
    "max_memory_tokens": 2000,
    "auto_inject": True,
    "block_recency": True,
    "block_recency_unit": "session",
}


def kernel_with_history(users):
    """A real kernel memory path whose users each wrote one row per
    session 1 to 6 (and one without a session), through the kernel's
    write path."""
    manager = _manager(KERNEL_CONFIG)
    for user in users:
        writes = [
            ("profile_agent", f"{user} lives in Tallinn", 1),
            ("task_agent", f"{user} works on the Juniper project", 2),
            ("calendar_agent", f"{user} has a sync in the Birch room", 3),
            ("profile_agent", f"{user} has a cat named Mochi", 4),
            ("task_agent", f"{user} pairs with Dana Whitfield", 5),
            ("calendar_agent", f"{user} talks at the Kestrel summit", 6),
            ("profile_agent", f"{user} uses Rocket Chat", None),
        ]
        for agent, content, session in writes:
            metadata = {
                "owner_agent": agent, "user_id": user,
                "memory_type": "profile", "sharing_policy": "shared",
            }
            if session is not None:
                metadata["session"] = session
            syscall = MemorySyscall(agent, MemoryQuery(
                operation_type="add_memory",
                params={"content": content, "metadata": metadata},
            ))
            manager.stamp_syscall(syscall)
            assert manager.address_request(syscall).success
    return manager


def without_timings(diagnostics: dict) -> dict:
    return {
        key: value for key, value in diagnostics.items()
        if not key.endswith("_ms")
    }


def test_kernel_block_equals_the_library_block_with_session_ages():
    users = ["alice", "bob", "carol"]
    manager = kernel_with_history(users)
    injector = ContextInjector(manager, KERNEL_CONFIG)
    # A replicated agent's copy, from the kernel's /memory/config report.
    library = MemoryPipeline(
        manager.provider,
        PipelineSettings.from_memory_config(
            manager.pipeline_settings().as_dict()
        ),
    )
    for user in users:
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user",
             "content": f"Where does {user} live and what is the cat?"},
        ]
        query = LLMQuery(messages=list(messages), action_type="chat")
        query, kernel_diag = injector.inject(
            AGENT, query, user_id=user, session=7,
        )
        library_messages, library_diag = library.inject(
            AGENT, list(messages), user_id=user, session=7,
        )
        assert query.messages == library_messages
        assert without_timings(kernel_diag) == without_timings(library_diag)
        block = query.messages[0]["content"]
        assert kernel_diag["injected_count"] == 7
        assert kernel_diag["session"] == 7
        assert kernel_diag["block_recency_unit"] == "session"
        assert f"- {user} lives in Tallinn (6 sessions ago)" in block
        assert f"- {user} talks at the Kestrel summit (1 session ago)" \
            in block
        assert f"- {user} uses Rocket Chat\n" in block + "\n"


def test_injector_passes_the_session_to_the_library():
    manager = MagicMock()
    manager.memory_pipeline.return_value.inject.return_value = (
        [], {"resolved_user_id": USER, "injected_count": 0},
    )
    injector = ContextInjector(manager, {"auto_inject": True})
    query = LLMQuery(
        messages=[{"role": "user", "content": "hi"}], action_type="chat",
    )
    inject = manager.memory_pipeline.return_value.inject
    injector.inject(AGENT, query, user_id=USER, session=7)
    assert inject.call_args.kwargs["session"] == 7
    injector.inject(AGENT, query, user_id=USER)
    assert inject.call_args.kwargs["session"] is None


def test_injector_budget_helper_uses_the_kernel_recency_unit():
    manager = MemoryManager.__new__(MemoryManager)
    manager.block_recency = True
    manager.block_recency_unit = "session"
    rows = [
        row("a", "first old row", timestamp="200001010000"),
        row("b", "second old row", timestamp="200001010000"),
    ]
    fits_without_ages = estimate_tokens(format_block(rows))
    injector = ContextInjector(
        manager, {"max_memory_tokens": fits_without_ages},
    )
    # Session ages need the current session, which the helper has not:
    # no age is added, so both rows fit (time ages would not).
    assert injector._truncate_by_token_budget(rows) == rows


# --- the conversation turn carries the session ------------------------


def test_conversation_request_merges_extra_metadata():
    fixed = {
        "user_id": USER, "owner_agent": AGENT,
        "memory_type": "conversation", "sharing_policy": "private",
    }
    assert conversation_request(AGENT, "hi", "hello", USER)["metadata"] \
        == fixed
    stamped = conversation_request(
        AGENT, "hi", "hello", USER, extra_metadata={"session": 7},
    )
    assert stamped["metadata"] == dict(fixed, session=7)
    note = conversation_note(
        AGENT, "hi", "hello", USER, extra_metadata={"session": 7},
    )
    assert note.metadata == dict(fixed, session=7)
    assert note.content == "User: hi\nAssistant: hello"


class InlineThread:
    """Runs the extractor's background write on ``start``."""

    def __init__(self, target, args, daemon):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


def test_kernel_conversation_turn_is_stamped_with_the_session():
    manager = _manager({"provider": "in-memory"})
    extractor = ConversationExtractor(manager, {"auto_extract": True})
    with patch(
        "aios.memory.conversation_extractor.threading.Thread",
        InlineThread,
    ):
        extractor.extract_async(
            AGENT, "where is the sync?", "Birch.", user_id=USER, session=7,
        )
        extractor.extract_async(
            AGENT, "and the offsite?", "Lisbon.", user_id=USER,
        )
    stamped, unstamped = manager.provider.list(USER, 10)
    assert stamped.metadata["session"] == 7
    assert stamped.metadata["memory_type"] == "conversation"
    assert "session" not in unstamped.metadata

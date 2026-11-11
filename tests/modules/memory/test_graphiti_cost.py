"""Graphiti's internal LLM and embedder calls count to their trial
(NeurIPS Subtask 16; docs/GRAPHITI_BACKEND.md, "LLM, embedder and
cost"). Graphiti is async; its client calls the synchronous
``litellm.completion`` in a worker thread on the runner's loop, and the
runner carries the caller's usage tag into the loop. An ``acompletion``
call would never reach the usage logger.
"""
import litellm
import pytest

from cerebrum.utils import graphiti as clients
from cerebrum.utils import usage
from tests.modules.memory.test_provider_contract import needs_ollama

BACKEND_LLM = {"provider": "azure_openai", "model": "gpt-4o",
               "temperature": 0.0, "seed": 7}


# LiteLLM copies a registered logger into these lists on its first call,
# and calls only the first usage logger it finds.
CALLBACK_LISTS = ("callbacks", "input_callback", "success_callback",
                  "failure_callback", "_async_success_callback",
                  "_async_failure_callback")


@pytest.fixture(autouse=True)
def callbacks():
    """Each test starts with no usage logger registered (so its own is
    the first) and leaves LiteLLM's lists as it found them: ``llm_client``
    registers the process's logger, as the kernel does, and a lingering
    one would take a later test's calls."""
    before = {name: list(getattr(litellm, name)) for name in CALLBACK_LISTS}
    # By name: usage._logger_class() defines a new class on every call,
    # and LiteLLM's own dedupe goes by the class name too.
    for name in CALLBACK_LISTS:
        getattr(litellm, name)[:] = [
            c for c in getattr(litellm, name)
            if type(c).__name__ != "LiteLLMUsageLogger"]
    yield
    for name, found in before.items():
        getattr(litellm, name)[:] = found


@pytest.fixture
def accumulator():
    fresh = usage.UsageAccumulator()
    callback = usage.install_litellm_logger(fresh)
    yield fresh
    litellm.callbacks.remove(callback)
    for tag in ("alice", "bob"):
        usage.ACCUMULATOR.take(tag, wait=0)


@pytest.fixture
def runner():
    runner = clients.GraphitiRunner()
    yield runner
    runner.close()


def test_llm_calls_count_to_the_trial_with_the_pinned_decoding(
        accumulator, runner, monkeypatch):
    """Each call is a ``backend_extraction`` record of the caller's
    trial, priced as ``azure/gpt-4o``; it asks for the response model's
    JSON schema at temperature 0 with the seed, and a fenced reply
    parses. An untagged call is counted to no trial."""
    from graphiti_core.prompts.extract_nodes import ExtractedEntities
    from graphiti_core.prompts.models import Message

    sent = []
    real = litellm.completion

    def mocked(**kwargs):
        sent.append(kwargs)
        return real(**kwargs, mock_response=(
            '```json\n{"extracted_entities": [{"name": "Slack", '
            '"entity_type_id": 0}]}\n```'))
    monkeypatch.setattr(litellm, "completion", mocked)
    client = clients.llm_client(BACKEND_LLM)
    with usage.tagged("alice"):
        reply = runner.run(client.generate_response,
                           [Message(role="user", content="extract")],
                           response_model=ExtractedEntities)
    runner.run(client.generate_response,
               [Message(role="user", content="extract")],
               response_model=ExtractedEntities)
    assert reply["extracted_entities"][0]["name"] == "Slack"
    records = accumulator.take("alice", wait=5.0)
    assert [(r["trial_tag"], r["purpose"], r["model"]) for r in records] == [
        ("alice", usage.BACKEND_EXTRACTION, "azure/gpt-4o")]
    assert records[0]["prompt_tokens"] > 0
    assert accumulator.take("bob", wait=0) == []
    assert sent[0]["model"] == "azure/gpt-4o"
    assert sent[0]["temperature"] == 0.0 and sent[0]["seed"] == 7
    assert sent[0]["response_format"]["type"] == "json_schema"
    assert sent[0]["response_format"]["json_schema"]["name"] == (
        "ExtractedEntities")


def test_the_llm_is_the_pinned_backend_llm():
    """Graphiti's LLM is ``memory.backend_llm`` for both model sizes;
    an unsupported provider is refused."""
    client = clients.llm_client(BACKEND_LLM)
    assert client.model == client.small_model == "azure/gpt-4o"
    assert client.litellm_model == "azure/gpt-4o"
    with pytest.raises(ValueError):
        clients.llm_client({"provider": "anthropic", "model": "x"})
    with pytest.raises(ValueError):
        clients.llm_client({"provider": "azure_openai"})


@needs_ollama
def test_embedding_calls_count_to_the_trial(runner):
    """The embedder is the pinned Ollama model, counted per trial
    through the runner."""
    embedder = clients.embedder({"provider": "ollama",
                                 "model": "nomic-embed-text",
                                 "dimension": 768,
                                 "ollama_base_url": "http://localhost:11434"})
    with usage.tagged("bob"):
        vectors = runner.run(embedder.create_batch, ["a fact", "another"])
        one = runner.run(embedder.create, ["a fact"])
    assert len(vectors) == 2 and len(vectors[0]) == 768
    assert one == pytest.approx(vectors[0], abs=1e-6)
    records = usage.ACCUMULATOR.take("bob", wait=5.0)
    assert [(r["purpose"], r["model"]) for r in records] == [
        (usage.EMBEDDING, "ollama/nomic-embed-text")] * 2

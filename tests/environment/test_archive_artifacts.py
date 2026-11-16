"""scripts/archive_artifacts.py (NeurIPS Subtask 17): nothing is copied
into repo-artifacts when a file holds a configured key value."""
import gzip
import importlib.util
import os
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / \
    "archive_artifacts.py"
KEY = "azure-test-key-0123456789abcdef"


@pytest.fixture
def archive(monkeypatch, tmp_path):
    """The script's ``main``, with the synthetic key the only configured
    value: a kernel checkout whose .env and config.yaml hold none, and no
    other secret-named variable in the environment."""
    spec = importlib.util.spec_from_file_location("archive_artifacts",
                                                  SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    root = tmp_path / "checkout"
    (root / "aios" / "config").mkdir(parents=True)
    (root / ".env").write_text("")
    (root / "aios" / "config" / "config.yaml").write_text("memory: {}\n")
    for name in list(os.environ):
        if module.secret_values(environ={name: "x" * 20}):
            monkeypatch.delenv(name)
    monkeypatch.setenv("FAKE_SERVICE_API_KEY", KEY)
    return lambda *args: module.main([*map(str, args), "--root", str(root)])


def logs(tmp_path, leak=None) -> Path:
    """A run's logs: a kernel log, a cell log in a subdirectory, and
    ``leak`` (a writer of one more file) when given."""
    root = tmp_path / "run" / "logs"
    (root / "cells").mkdir(parents=True)
    (root / "kernel_qwen.log").write_text("INFO started\n")
    (root / "cells" / "h0.log").write_text("trial 0 done\n")
    if leak:
        leak(root)
    return root


def test_a_clean_run_is_copied(archive, tmp_path, capsys):
    source = logs(tmp_path)
    dest = tmp_path / "artifacts" / "run1"
    assert archive("--dest", dest, source) == 0
    assert (dest / "logs" / "cells" / "h0.log").read_text() == \
        "trial 0 done\n"
    assert (source / "kernel_qwen.log").is_file()  # the source is kept
    assert "2 file(s) scanned" in capsys.readouterr().out


def zipped(directory: Path) -> None:
    with zipfile.ZipFile(directory / "replay.zip", "w",
                         zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("replay/m1.log", f"api_key={KEY}\n")


LEAKS = {
    "text": lambda d: (d / "cells" / "h2.log").write_text(
        f"Traceback ... api_key={KEY!r}\n"),
    "gzip": lambda d: (d / "old.log.gz").write_bytes(
        gzip.compress(f"api_key={KEY}\n".encode())),
    "zip": zipped,
    # the key across the boundary of two reads
    "split": lambda d: (d / "big.log").write_bytes(
        b"x" * ((1 << 20) - 10) + KEY.encode() + b"\n"),
    # LiteLLM's Azure debug line: the key's first 8 characters
    "head": lambda d: (d / "debug.log").write_text(
        f"Api Base: https://x.test/, Api Key:{KEY[:8]}***************\n"),
    # a report that cut a long string through the key
    "cut": lambda d: (d / "replay.log").write_text(
        f"command = 'curl -H api-key: {KEY[:15]}...yyyy'\n"),
    # LiteLLM's masker: the first and last 4 beside asterisks
    "masked": lambda d: (d / "curl.log").write_text(
        f"-H 'api-key: {KEY[:4]}****{KEY[-4:]}'\n"),
}


@pytest.mark.parametrize("leak", sorted(LEAKS))
def test_a_file_holding_a_key_refuses_the_copy(archive, tmp_path, capsys,
                                               leak):
    source = logs(tmp_path, LEAKS[leak])
    dest = tmp_path / "artifacts" / "run1"
    assert archive("--dest", dest, source) == 2
    assert not dest.exists()  # nothing copied
    out = capsys.readouterr()
    assert "refused" in out.err and "nothing copied" in out.err
    shown = out.out + out.err  # the file is named, no run of the key
    assert not any(KEY[i:i + 8] in shown for i in range(len(KEY) - 7))
    (named,) = [line for line in out.err.splitlines()
                if "holds a configured key value" in line]
    assert str(source) in named


@pytest.mark.parametrize("where, text", [
    (".env", "AZURE_API_KEY={}\n"),
    ("aios/config/config.yaml", "api_keys:\n  openai: {}\n"),
], ids=["env_file", "config_yaml"])
def test_a_key_kept_only_in_the_checkout_is_looked_for(
        archive, tmp_path, capsys, where, text):
    """The checkout's ``.env`` and ``config.yaml`` are read as well as
    the environment: the drivers source ``.env`` only into the harness's
    subshell, so at the archive step the Azure key and the Neo4j
    password are in the file alone unless the shell exports them
    (Subtask 17)."""
    other = "file-only-key-9876543210zyxwvu"
    (tmp_path / "checkout" / where).write_text(text.format(other))
    source = logs(tmp_path, lambda d: (d / "cells" / "h2.log").write_text(
        f"api_key={other}\n"))
    dest = tmp_path / "artifacts" / "run1"
    assert archive("--dest", dest, source) == 2
    assert not dest.exists()
    assert "holds a configured key value" in capsys.readouterr().err


def test_sums_list_every_archived_file(archive, tmp_path):
    """``--sums``: SHA256SUMS in the destination, as sha256sum prints
    it, over everything there, an earlier archive's files included."""
    import hashlib

    dest = tmp_path / "artifacts"
    assert archive("--dest", dest, "--sums", logs(tmp_path)) == 0
    driver = tmp_path / "driver.log"
    driver.write_text("done\n")
    assert archive("--dest", dest, "--sums", driver) == 0
    lines = (dest / "SHA256SUMS").read_text().splitlines()
    assert [line.split("  ")[1] for line in lines] == [
        "./driver.log", "./logs/cells/h0.log", "./logs/kernel_qwen.log"]
    assert lines[0].split("  ")[0] == hashlib.sha256(b"done\n").hexdigest()


def test_an_existing_target_is_not_overwritten(archive, tmp_path, capsys):
    source = logs(tmp_path)
    dest = tmp_path / "artifacts"
    (dest / "logs").mkdir(parents=True)
    (dest / "logs" / "earlier.log").write_text("kept\n")
    assert archive("--dest", dest, source) == 2
    assert "would overwrite" in capsys.readouterr().err
    assert sorted(p.name for p in (dest / "logs").iterdir()) == \
        ["earlier.log"]


def test_check_names_the_files_and_copies_nothing(archive, tmp_path,
                                                  capsys):
    source = logs(tmp_path, LEAKS["text"])
    assert archive("--check", source) == 2
    err = capsys.readouterr().err
    assert "h2.log" in err and "kernel_qwen.log" not in err
    assert archive("--check", logs(tmp_path / "clean")) == 0


def test_no_key_to_look_for_refuses(archive, tmp_path, monkeypatch,
                                    capsys):
    """A scan for nothing would pass every file: with no configured key
    value (no .env, an unset environment) the copy is refused."""
    monkeypatch.delenv("FAKE_SERVICE_API_KEY")
    dest = tmp_path / "artifacts"
    assert archive("--dest", dest, logs(tmp_path)) == 2
    assert "no configured key value" in capsys.readouterr().err
    assert not dest.exists()

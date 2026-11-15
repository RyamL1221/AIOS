# Copies run artifacts into repo-artifacts only when no file holds a key.
"""Archive run artifacts, refusing any file that holds a key value.

Nothing goes into ``repo-artifacts/`` but through this script (NeurIPS
Subtask 17): the drivers archive their logs with it (``ARCHIVE``), and
the mutation runs archive their mutants, results and replay logs with
it. Every configured key value is looked for in every file, compressed
ones read through (``.gz``, ``.bz2``, ``.xz``, ``.zip``): those of the
environment's secret-named variables and of the secret-named keys of the
kernel checkout's ``.env`` and ``aios/config/config.yaml``
(``aios.utils.redact.secret_values``), and with each value its
fragments, by the rule the logs are redacted with
(``aios.utils.redact.holds_secret``: 8 consecutive characters of a long
secret, or a shorter head or tail beside a mask). If one is found the
copy is refused and nothing is copied; the files are named, the values
never printed. Files are read as bytes: a value in another encoding
(UTF-16, base64) is not found.

The sources are first copied to a staging directory (in the system's
temporary directory); that copy is scanned and, only when clean, moved
into ``--dest``, so a log still being written cannot change between the
scan and the copy. An existing target is never overwritten.

    python scripts/archive_artifacts.py --dest ../repo-artifacts/X SRC...
    python scripts/archive_artifacts.py --check PATH...   # scan only

``--sums`` then writes ``SHA256SUMS`` in ``--dest``: every file under it,
earlier archives' included, as ``sha256sum`` prints them.

Exit status: 0 copied (or clean), 2 refused, 1 a usage error.
"""
import argparse
import bz2
import gzip
import hashlib
import lzma
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aios.utils.redact import (  # noqa: E402
    file_secret_configs,
    holds_secret,
    secret_values,
)

CHUNK = 1 << 20
OPENERS = {".gz": gzip.open, ".tgz": gzip.open, ".bz2": bz2.open,
           ".xz": lzma.open}


# What two reads share, so that a value, or a masked end with its mask,
# split across them is still found: the longest value and this margin.
OVERLAP_MARGIN = 64


def key_values(root: Path) -> tuple:
    """Every configured key value: the environment's and the checkout's
    ``.env`` and ``config.yaml``'s."""
    return secret_values(*file_secret_configs(root))


def _stream_holds(stream, values) -> bool:
    keep = max(map(len, values)) + OVERLAP_MARGIN
    tail = b""
    while True:
        chunk = stream.read(CHUNK)
        if not chunk:
            return False
        window = tail + chunk
        # Latin-1 maps each byte to one character, so the redaction's
        # own rule reads the bytes as they are.
        if holds_secret(window.decode("latin-1"), values):
            return True
        tail = window[-keep:]


def file_holds(path: Path, values) -> bool:
    """Whether the file, or what it compresses, holds one of ``values``
    or a fragment of one. A file that cannot be read through is read as
    it is."""
    with open(path, "rb") as stream:
        if _stream_holds(stream, values):
            return True
    opener = OPENERS.get(path.suffix.lower())
    try:
        if opener is not None:
            with opener(path, "rb") as stream:
                return _stream_holds(stream, values)
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    with archive.open(name) as stream:
                        if _stream_holds(stream, values):
                            return True
    except (OSError, EOFError, lzma.LZMAError, zipfile.BadZipFile):
        pass
    return False


def files_under(paths) -> list:
    out = []
    for path in map(Path, paths):
        if path.is_dir():
            out.extend(sorted(p for p in path.rglob("*") if p.is_file()))
        elif path.is_file():
            out.append(path)
    return out


def holding(paths, values) -> list:
    """The files under ``paths`` that hold one of ``values`` or a
    fragment of one."""
    return [p for p in files_under(paths) if file_holds(p, values)]


def archive(sources, dest: Path, values) -> list:
    """Copy each source into ``dest`` (under its own name) when no file
    of any holds one of ``values``; return the source files that do
    (nothing is copied then)."""
    targets = [dest / Path(s).name for s in sources]
    taken = [t for t in targets if t.exists()]
    if taken:
        raise FileExistsError(", ".join(map(str, taken)))
    stage = Path(tempfile.mkdtemp(prefix="archive_artifacts_"))
    try:
        for source in map(Path, sources):
            if source.is_dir():
                shutil.copytree(source, stage / source.name)
            else:
                shutil.copy2(source, stage / source.name)
        found = holding([stage], values)
        if found:
            by_name = {Path(s).name: Path(s) for s in sources}
            return [by_name[p.relative_to(stage).parts[0]].joinpath(
                        *p.relative_to(stage).parts[1:]) for p in found]
        dest.mkdir(parents=True, exist_ok=True)
        for source in map(Path, sources):
            shutil.move(str(stage / source.name), str(dest / source.name))
        return []
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def write_sums(dest: Path) -> None:
    """``dest/SHA256SUMS``: each file under ``dest`` but itself, sorted,
    as ``<sha256>  ./<path>``."""
    lines = []
    for path in sorted(p for p in dest.rglob("*") if p.is_file()):
        if path == dest / "SHA256SUMS":
            continue
        digest = hashlib.sha256()
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(CHUNK), b""):
                digest.update(chunk)
        lines.append(f"{digest.hexdigest()}  ./{path.relative_to(dest)}")
    (dest / "SHA256SUMS").write_text("\n".join(lines) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="+")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dest", type=Path,
                      help="copy the paths here, when none holds a key")
    mode.add_argument("--check", action="store_true",
                      help="scan only: name the files that hold a key")
    parser.add_argument("--sums", action="store_true",
                        help="write SHA256SUMS in --dest after the copy")
    parser.add_argument("--root", type=Path, default=ROOT,
                        help="the AIOS checkout whose .env and config.yaml "
                             "hold the keys (default: this one)")
    args = parser.parse_args(argv)
    missing = [p for p in args.paths if not Path(p).exists()]
    if missing:
        print(f"archive: no such path: {', '.join(missing)}", file=sys.stderr)
        return 1
    values = key_values(args.root)
    if not values:
        print("archive: refused: no configured key value to look for "
              f"(none in the environment or {args.root}'s .env and "
              "config.yaml)", file=sys.stderr)
        return 2
    if args.check:
        found = holding(args.paths, values)
    else:
        try:
            found = archive(args.paths, args.dest, values)
        except FileExistsError as error:
            print(f"archive: refused: would overwrite {error}",
                  file=sys.stderr)
            return 2
    for path in found:
        print("archive: holds a configured key value or a fragment of one: "
              f"{path}", file=sys.stderr)
    if found:
        print(f"archive: refused: {len(found)} file(s) hold a key value; "
              "nothing copied" if not args.check else
              f"archive: {len(found)} file(s) hold a key value",
              file=sys.stderr)
        return 2
    if args.dest is not None and args.sums:
        write_sums(args.dest)
    scanned = len(files_under(args.paths))
    print(f"archive: {scanned} file(s) scanned, none holds a key value"
          + ("" if args.check else f"; copied to {args.dest}"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

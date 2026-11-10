"""
The value matcher: the one rule every benchmark v2 check uses, and the
rule the library's forget, sweep and read guard act on
(docs/DELETION_AND_SUPERSESSION.md, "The matcher, shared").

It lives here, in the library, and the benchmark's scorer (Cerebrum
``benchmarks/shared_memory/probes.py``) re-exports it, loading this file
from the AIOS checkout: one copy of the code, so whatever the scorer
counts as exposure is what the forget removes. ``PIPELINE_VERSION``
covers it with the rest of the package. Standard library only, like
every module of the library (no ``cerebrum`` import).

Text is casefolded, accents are stripped, and runs of whitespace and
the punctuation ``-`` ``_`` ``.`` ``/`` collapse to one space. A value
matches when it appears with a non-alphanumeric character, or the
text's start or end, on each side.
"""
import re
import unicodedata
from typing import Iterable, Optional

_COLLAPSE = re.compile(r"[\s\-_./]+")


def normalize(text: Optional[str]) -> str:
    """``text`` casefolded, without accents, with whitespace and
    ``- _ . /`` runs collapsed to one space."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    plain = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _COLLAPSE.sub(" ", plain.casefold()).strip()


def value_in(text: Optional[str], value: Optional[str]) -> bool:
    """Whether ``value`` appears in ``text`` under the matcher."""
    needle = normalize(value)
    if not needle:
        return False
    pattern = r"(?<![0-9a-z])" + re.escape(needle) + r"(?![0-9a-z])"
    return re.search(pattern, normalize(text)) is not None


def match_forms(text: Optional[str],
                forms: Iterable[Optional[str]]) -> Optional[str]:
    """The first of ``forms`` that appears in ``text`` (as given), or
    None. Empty forms never match."""
    for form in forms:
        if form and value_in(text, form):
            return form
    return None


def match_any(text: Optional[str], value: Optional[str],
              aliases: Iterable[str] = ()) -> Optional[str]:
    """The first of ``value`` and its ``aliases`` that appears in
    ``text`` (as given), or None."""
    return match_forms(text, [value, *aliases])

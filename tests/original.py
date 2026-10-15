"""Load the pre-cleanup program, so a regression test can be shown failing.

The original is a single self-contained module that does nothing at import
time, so there is no need to transcribe it: the baseline commit is read
straight out of git, written to a scratch file and imported under its own
name. Its `DB_FILE` global is the only thing that has to be redirected, and
`with_db()` does that.

The baseline is found by its commit subject rather than by hash, so the tests
survive the branch being rebased. If it cannot be found -- a checkout with no
git directory, say -- every test that needs it skips rather than fails.
"""

import contextlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

BASELINE_SUBJECT = "Initial commit"
PROJECT_ROOT = Path(__file__).resolve().parent.parent

_cache = {}


def _git(*args):
    return subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), *args],
        capture_output=True, text=True, encoding="utf-8", check=True,
    ).stdout


def baseline_commit():
    """The commit the cleanup started from, looked up by its subject."""
    out = _git("log", "--format=%H %s")
    matches = [
        line.split(" ", 1)[0]
        for line in out.splitlines()
        if line.split(" ", 1)[1:] and line.split(" ", 1)[1].strip() == BASELINE_SUBJECT
    ]
    if len(matches) != 1:
        raise LookupError(
            f"expected exactly one commit titled {BASELINE_SUBJECT!r}, found {len(matches)}"
        )
    return matches[0]


def load():
    """Import the baseline `library_system.py` as a module object."""
    if "module" in _cache:
        return _cache["module"]
    source = _git("show", f"{baseline_commit()}:library_system.py")
    scratch = Path(tempfile.mkdtemp(prefix="lms-baseline-")) / "original_library_system.py"
    scratch.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("original_library_system", scratch)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _cache["module"] = module
    return module


def available():
    try:
        load()
        return True
    except Exception:
        return False


requires_original = unittest.skipUnless(
    available(), "the baseline commit could not be read from git"
)


@contextlib.contextmanager
def with_db():
    """Point the baseline module at a scratch database for the duration."""
    module = load()
    previous = module.DB_FILE
    directory = tempfile.mkdtemp(prefix="lms-baseline-db-")
    module.DB_FILE = str(Path(directory) / "library.db")
    try:
        module.init_db()
        yield module
    finally:
        module.DB_FILE = previous

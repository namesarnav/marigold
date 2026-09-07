"""The prior path must import without PyTorch.

Until a model is trained on Marigold's own concepts, every user is served by
the cold-start prior — arithmetic on a Beta posterior, needing neither torch nor
numpy. The backend therefore ships `ml/` without the SAKT dependencies, and a
single module-level `import torch` anywhere in the import graph of
`ml.inference.predict` silently undoes that: the code still works in
development, where torch is installed, and the API image quietly gains ~2GB.

Run in a subprocess with the heavy modules blocked, rather than by manipulating
`sys.meta_path` in-process — the import graph has to be exercised from cold, and
this suite has already imported torch by the time it gets here.
"""

import subprocess
import sys
import textwrap

import pytest

# Everything the serving image is expected not to need.
HEAVY = ["torch", "numpy", "pandas", "sklearn", "scipy", "sentence_transformers", "transformers"]


def _run_with_heavy_deps_blocked(body: str) -> subprocess.CompletedProcess:
    script = textwrap.dedent(
        f"""
        import sys
        from importlib.abc import MetaPathFinder

        HEAVY = {HEAVY!r}

        class Blocker(MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.split(".")[0] in HEAVY:
                    raise ImportError(fullname + " is blocked")
                return None

        sys.meta_path.insert(0, Blocker())
        """
    ) + textwrap.dedent(body)

    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
    )


def test_predict_imports_without_torch_or_numpy():
    result = _run_with_heavy_deps_blocked(
        """
        import ml.inference.predict  # noqa: F401
        print("imported")
        """
    )
    assert result.returncode == 0, (
        "ml.inference.predict pulled in a heavy dependency at import time. "
        "Something in its import graph gained a module-level import of torch, "
        "numpy or similar; move it inside the function that needs it.\n\n"
        + result.stderr
    )
    assert "imported" in result.stdout


def test_the_prior_path_ranks_without_torch_or_numpy():
    """Importing clean is not enough — the cold-start path has to actually run."""
    result = _run_with_heavy_deps_blocked(
        """
        from datetime import datetime, timezone
        from ml.inference.predict import ForgettingRanker

        ranker = ForgettingRanker()
        scored = ranker.rank(
            "u1", ["algebra", "photosynthesis"],
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            history=[],
        )
        assert [s.source for s in scored] == ["prior", "prior"], scored
        print("ranked", len(scored))
        """
    )
    assert result.returncode == 0, result.stderr
    assert "ranked 2" in result.stdout


def test_the_guard_itself_fires():
    """The blocker must really block, or both tests above pass vacuously."""
    result = _run_with_heavy_deps_blocked("import torch")

    assert result.returncode != 0
    assert "blocked" in result.stderr

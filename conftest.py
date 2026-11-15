"""Global pytest configuration and monkeypatches for Windows Python 3.13."""

try:
    import _pytest.pathlib
    _pytest.pathlib.cleanup_dead_symlinks = lambda root: None
except Exception:
    pass

try:
    import _pytest.tmpdir
    _pytest.tmpdir.cleanup_dead_symlinks = lambda root: None
except Exception:
    pass

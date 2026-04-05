from __future__ import annotations

import importlib.util
import pathlib
import sys


def _load_install_smoke_module():
    path = pathlib.Path("tests/packaging/install_smoke.py")
    spec = importlib.util.spec_from_file_location("tests.packaging.install_smoke", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


install_smoke = _load_install_smoke_module()


def test_select_wheel_prefers_newest_build_over_lexicographic_order(tmp_path) -> None:
    older_newer_version = tmp_path / "pi_rpc_python-1.10.0-py3-none-any.whl"
    stale_lexicographically_later = tmp_path / "pi_rpc_python-1.2.0-py3-none-any.whl"
    older_newer_version.write_text("newer version but older build", encoding="utf-8")
    stale_lexicographically_later.write_text("stale wheel", encoding="utf-8")

    install_smoke.os.utime(older_newer_version, ns=(1_000_000_000, 1_000_000_000))
    install_smoke.os.utime(stale_lexicographically_later, ns=(2_000_000_000, 2_000_000_000))

    rebuilt_current_wheel = tmp_path / "pi_rpc_python-1.10.0-py3-none-any.whl"
    install_smoke.os.utime(rebuilt_current_wheel, ns=(3_000_000_000, 3_000_000_000))

    selected = install_smoke.select_built_wheel(tmp_path.glob("*.whl"))

    assert selected == rebuilt_current_wheel

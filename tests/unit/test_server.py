"""Server: active-controller counting (with pruning) and panel/debug content."""
import os
import time
import importlib.util

_SERVE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'server', 'serve.py')


def _load_serve():
    spec = importlib.util.spec_from_file_location('serve', _SERVE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_active_controllers_counts_recent_and_prunes_stale():
    srv = _load_serve()
    srv._known.clear()
    srv._known['aa'] = time.time()
    srv._known['bb'] = time.time()
    srv._known['cc'] = time.time() - (srv.CONTROLLER_TIMEOUT_S + 5)
    assert srv._active_controllers() == 2
    assert 'cc' not in srv._known        # stale entry pruned


def test_panel_solo_is_release_only():
    srv = _load_serve()
    assert 'Release Solo' in srv.PANEL_HTML
    assert 'toggleSolo' not in srv.PANEL_HTML


def test_debug_page_has_log_deploy_and_count():
    srv = _load_serve()
    assert 'CONTROLLERS IN MESH' in srv.DEBUG_HTML
    assert 'Push Firmware' in srv.DEBUG_HTML
    assert 'SERVER + MESH LOG' in srv.DEBUG_HTML
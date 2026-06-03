from server import firmware


def _write(root, name, content):
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_version_changes_with_content(tmp_path):
    files = ['a.py', 'b.py']
    _write(tmp_path, 'a.py', 'print(1)')
    _write(tmp_path, 'b.py', 'print(2)')
    v1 = firmware.current_version(tmp_path, files)
    _write(tmp_path, 'b.py', 'print(3)')
    v2 = firmware.current_version(tmp_path, files)
    assert v1 != v2
    assert len(v1) == firmware.VERSION_LEN


def test_version_stable_when_unchanged(tmp_path):
    files = ['a.py']
    _write(tmp_path, 'a.py', 'x = 1')
    assert firmware.current_version(tmp_path, files) == firmware.current_version(tmp_path, files)


def test_secrets_excluded_from_version(tmp_path):
    files = ['main.py', 'secrets.py']
    _write(tmp_path, 'main.py', 'code')
    _write(tmp_path, 'secrets.py', 'PASSWORD="a"')
    v1 = firmware.current_version(tmp_path, files)
    _write(tmp_path, 'secrets.py', 'PASSWORD="b"')   # credential change
    assert firmware.current_version(tmp_path, files) == v1   # not a firmware change


def test_manifest_lists_present_files_and_version(tmp_path):
    files = ['a.py', 'missing.py']
    _write(tmp_path, 'a.py', 'x')
    m = firmware.manifest(tmp_path, files)
    assert [f['path'] for f in m['files']] == ['a.py']
    assert m['version'] == firmware.current_version(tmp_path, files)

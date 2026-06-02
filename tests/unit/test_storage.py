"""state.json persistence. _FILE is pointed at a tmp file by conftest."""
import storage


def test_round_trip():
    storage.save({'theme': 2, 'scenes': [1, 0, 1]})
    assert storage.load({'theme': 0, 'scenes': [0, 0, 0]}) == {'theme': 2, 'scenes': [1, 0, 1]}


def test_missing_file_returns_defaults():
    defaults = {'theme': 0, 'scenes': [0, 0, 0]}
    loaded = storage.load(defaults)
    assert loaded == defaults
    assert loaded is not defaults   # a copy, not the same object


def test_missing_keys_filled_from_defaults():
    storage.save({'theme': 1})
    loaded = storage.load({'theme': 0, 'scenes': [0, 0, 0]})
    assert loaded['theme'] == 1
    assert loaded['scenes'] == [0, 0, 0]

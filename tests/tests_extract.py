from pipeline import extract as ex

BOOTSTRAP = {
    "events": [
        {"id": 1, "finished": True},
        {"id": 2, "finished": True},
        {"id": 3, "finished": False},
    ]
}


def _patch_api(monkeypatch, calls):
    monkeypatch.setattr(ex, "fetch_bootstrap", lambda s: BOOTSTRAP)
    monkeypatch.setattr(ex, "fetch_fixtures", lambda s: [])
    monkeypatch.setattr(ex, "fetch_live", lambda s, gw: calls.append(gw) or {"elements": []})
    monkeypatch.setattr(ex.time, "sleep", lambda _: None)


def test_finished_gameweeks():
    assert ex.finished_gameweeks(BOOTSTRAP) == [1, 2]


def test_extract_fetches_only_finished_gameweeks(monkeypatch):
    calls = []
    _patch_api(monkeypatch, calls)
    payload = ex.extract(session=object())
    assert calls == [1, 2]
    assert set(payload["live"]) == {1, 2}


def test_extract_skips_already_loaded_gameweeks(monkeypatch):
    calls = []
    _patch_api(monkeypatch, calls)
    payload = ex.extract(session=object(), skip={1})
    assert calls == [2]
    assert list(payload["live"]) == [2]


def test_save_raw_writes_files(monkeypatch, tmp_path):
    calls = []
    _patch_api(monkeypatch, calls)
    payload = ex.extract(session=object())
    ex.save_raw(payload, tmp_path)
    assert (tmp_path / "bootstrap-static.json").exists()
    assert (tmp_path / "fixtures.json").exists()
    assert (tmp_path / "live" / "gw1.json").exists()
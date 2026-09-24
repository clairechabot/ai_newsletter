from briefing.sources.base import safe_fetch

def test_safe_fetch_returns_items_on_success():
    out = safe_fetch("ok", lambda: ["a", "b"])
    assert out == ["a", "b"]

def test_safe_fetch_swallows_errors_to_empty_list(capsys):
    def boom():
        raise RuntimeError("dead site")
    out = safe_fetch("BadSite", boom)
    assert out == []
    assert "BadSite" in capsys.readouterr().out  # logged, not raised

def test_failure_emits_actions_warning_and_report(capsys, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    report = {}
    safe_fetch("Bad", lambda: (_ for _ in ()).throw(RuntimeError("403\nForbidden")), report)
    out = capsys.readouterr().out
    assert "::warning title=Source failed: Bad::403%0AForbidden" in out
    assert report["Bad"].startswith("FAILED")

def test_no_warning_outside_actions(capsys, monkeypatch):
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    safe_fetch("Bad", lambda: 1 / 0)
    assert "::warning" not in capsys.readouterr().out

def test_step_summary_table(tmp_path, monkeypatch):
    from briefing.sources.base import write_step_summary
    p = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(p))
    report = {}
    safe_fetch("Good", lambda: ["a", "b"], report)
    safe_fetch("Empty", lambda: [], report)
    safe_fetch("Bad", lambda: 1 / 0, report)
    write_step_summary(report)
    text = p.read_text()
    assert "| Good | 2 items |" in text
    assert "| Empty | ⚠️ 0 items |" in text
    assert "| Bad | ❌ FAILED" in text

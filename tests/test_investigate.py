import json

from starter import investigate as inv
from starter import parallel


def test_primary_domains_are_courts_government_filings_and_archives():
    primary = [
        "https://www.sec.gov/Archives/edgar/data/1",
        "https://find-and-update.company-information.service.gov.uk/company/1",
        "https://www.nvcourts.gov/case/1",
        "https://web.archive.org/web/2024/x",
        "https://www.legislation.gov.uk/ukpga/2006/46",
        "https://investors.newscorp.com/news",
        "https://media.investor.foxcorporation.com/x",
        "https://example.com/press-releases/2024",
    ]
    secondary = [
        "https://www.nytimes.com/2024/12/09/business/murdoch.html",
        "https://www.courthousenews.com/murdoch",
        "https://someone.substack.com/p/gov",
    ]
    assert all(inv.is_primary(u) for u in primary)
    assert not any(inv.is_primary(u) for u in secondary)


Q = {"id": "q1", "text": "When was the ruling?", "kind": "date"}


def _claim(i, value, sid=None):
    return {"id": f"c{i}", "source_id": sid or f"s{i}", "question_id": "q1", "normalized": value}


def test_two_differing_dates_are_a_conflict_with_the_primary_value():
    claims = [_claim(1, "2024-12-09"), _claim(2, "2024-12-07"), _claim(3, "2024-12")]
    k = inv.find_conflict(Q, claims, primary_ids={"s1"})
    assert k["values"] == ["2024-12-07", "2024-12-09"]
    assert k["claim_ids"] == ["c1", "c2", "c3"]
    assert k["primary_value"] == "2024-12-09"


def test_a_coarser_date_agrees_with_a_finer_one():
    assert inv.find_conflict(Q, [_claim(1, "2024-12"), _claim(2, "2024-12-09")], set()) is None
    number = {**Q, "kind": "number"}  # prefix agreement is for dates only
    assert inv.find_conflict(number, [_claim(1, "3"), _claim(2, "33")], set())["values"]
    agree = [("39", "38.9"), ("3300000000", "3330000000"), ("36", "36.2")]
    for a, b in agree:  # rounding is agreement
        assert inv.find_conflict(number, [_claim(1, a), _claim(2, b)], set()) is None
    assert inv.find_conflict(number, [_claim(1, "33"), _claim(2, "36")], set())


def test_a_claim_whose_quote_is_not_in_the_excerpt_is_dropped(monkeypatch):
    rows = [
        {
            "source_id": "s1",
            "value": "9 Dec",
            "normalized": "2024-12-09",
            "quote": "ruled  ON 9 dec",
        },
        {
            "source_id": "s2",
            "value": "7 Dec",
            "normalized": "2024-12-07",
            "quote": "invented 7 Dec quote",
        },
        {"source_id": "s1", "value": "soon", "normalized": "soon", "quote": "ruled on 9 Dec"},
        {"source_id": "s2", "value": "x", "normalized": "2024-12-07", "quote": "A ruling came"},
    ]
    answer = "```json\n" + json.dumps(rows) + "\n```"
    monkeypatch.setattr(parallel, "respond", lambda *a, **k: {"text": answer, "sources": []})
    excerpts = {"s1": "The commissioner ruled on\n9 Dec 2024.", "s2": "A ruling came in December."}
    assert [c["source_id"] for c in inv._claims(Q, excerpts)] == ["s1"]


def test_investigate_streams_the_contract_with_stubbed_search_and_respond(monkeypatch):
    def respond(prompt, effort="low", schema=None):
        if "Investigative premise" in prompt:
            data = {
                "entities": [{"name": "A", "kind": "person"}],
                "questions": [
                    {"text": "When was it?", "kind": "date"},
                    {"text": "Why?", "kind": "date"},
                ],
            }
        elif "Question:" in prompt:
            data = [
                {"source_id": "s1", "value": "v", "normalized": "2024-12-09", "quote": "on 9 Dec"},
                {"source_id": "s2", "value": "v", "normalized": "2024-12-07", "quote": "on 7 Dec"},
            ]
        else:
            return {"text": "Sources disagree.", "sources": []}
        return {"text": json.dumps(data), "sources": []}

    def search(objective, queries, max_results=5):
        if objective.startswith("Primary"):
            raise OSError("down")
        return [
            {
                "url": "https://a.com/1",
                "title": "a",
                "publish_date": None,
                "excerpts": ["on 9 Dec"],
            },
            {"url": "https://sec.gov/2", "title": "b", "excerpts": ["on 7 Dec"]},
        ]

    monkeypatch.setattr(parallel, "respond", respond)
    monkeypatch.setattr(parallel, "search", search)
    events = list(inv.investigate("p"))
    assert [e["type"] for e in events if e["type"] != "stats"] == [
        "entity",
        "question",
        "error",
        "verdict",
    ]

    monkeypatch.setattr(parallel, "search", lambda o, q, m=5: search("", q))
    events = list(inv.investigate("p"))
    kinds = [e["type"] for e in events if e["type"] != "stats"]
    assert kinds == [
        "entity",
        "question",
        "source",
        "source",
        "claim",
        "claim",
        "conflict",
        "verdict",
    ]
    conflict = next(e for e in events if e["type"] == "conflict")
    assert conflict["primary_value"] == "2024-12-07" and conflict["id"] == "k1"
    assert events[-1] == {**events[-1], "type": "stats", "sources": 2, "claims": 2, "conflicts": 1}


def test_replay_streams_the_saved_run_without_login(client, tmp_path, monkeypatch):
    saved = [{"type": "entity", "id": "e1", "name": "A", "kind": "person"}, {"type": "verdict"}]
    (tmp_path / "demo.json").write_text(json.dumps(saved))
    monkeypatch.setattr(inv, "RUNS", tmp_path)
    monkeypatch.setattr(inv, "REPLAY_DELAY", 0)
    r = client.get("/api/investigate/replay?name=demo")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert [json.loads(b[6:]) for b in r.text.strip().split("\n\n")] == saved
    assert client.get("/api/investigate/replay?name=../demo").status_code == 404
    assert client.get("/api/investigate").status_code == 422

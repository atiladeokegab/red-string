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


def _answer(monkeypatch, rows):
    text = json.dumps({"claims": rows})
    monkeypatch.setattr(parallel, "respond", lambda *a, **k: {"text": text, "sources": []})


def test_a_percentage_does_not_answer_a_head_count_and_the_reverse(monkeypatch):
    rows = [
        {"source_id": "s1", "value": "97%", "normalized": "97", "quote": "97% of staff signed"},
        {"source_id": "s2", "value": "747", "normalized": "747", "quote": "747 employees signed"},
    ]
    _answer(monkeypatch, rows)
    excerpts = {"s1": "97% of staff signed", "s2": "747 employees signed"}
    many = {"id": "q1", "text": "How many employees signed?", "kind": "number"}
    share = {"id": "q1", "text": "What percentage of employees signed?", "kind": "number"}
    assert [c["source_id"] for c in inv._claims(many, excerpts)] == ["s2"]
    assert [c["source_id"] for c in inv._claims(share, excerpts)] == ["s1"]


def test_a_normalized_value_the_quote_does_not_state_is_dropped(monkeypatch):
    number = {"id": "q1", "text": "How many people signed?", "kind": "number"}
    rows = [
        {
            "source_id": "s1",
            "value": "999",
            "normalized": "999",
            "quote": "Exactly 6 people signed.",
        },
        {"source_id": "s2", "value": "six", "normalized": "6", "quote": "six people signed"},
        {
            "source_id": "s3",
            "value": "$3.3bn",
            "normalized": "3300000000",
            "quote": "paid $3.3 billion",
        },
    ]
    _answer(monkeypatch, rows)
    excerpts = {
        "s1": "Exactly 6 people signed.",
        "s2": "six people signed",
        "s3": "paid $3.3 billion",
    }
    assert [c["source_id"] for c in inv._claims(number, excerpts)] == ["s2", "s3"]

    rows = [
        {
            "source_id": "s1",
            "value": "Dec 9",
            "normalized": "2024-12-07",
            "quote": "ruled on Dec 9",
        },
        {
            "source_id": "s2",
            "value": "Dec 9",
            "normalized": "2024-12-09",
            "quote": "ruled on Dec 9",
        },
        {
            "source_id": "s3",
            "value": "Sat",
            "normalized": "2024-12-07",
            "quote": "filed on Saturday",
        },
        {
            "source_id": "s4",
            "value": "Sat",
            "normalized": "2024-12-08",
            "quote": "filed on Saturday",
        },
    ]
    _answer(monkeypatch, rows)
    excerpts = {"s1": "ruled on Dec 9", "s2": "ruled on Dec 9"}
    excerpts |= {"s3": "filed on Saturday", "s4": "filed on Saturday"}
    assert [c["source_id"] for c in inv._claims(Q, excerpts)] == ["s2", "s3"]

    # the magnitude and every date part the quote states must match, not only digits or the day
    assert not inv.grounded("Exactly 6 people signed.", "600", number)
    assert inv.grounded("a £57.75m settlement", "57750000", number)
    assert inv.grounded("sold 16,835,016 shares", "16835016", number)
    assert not inv.grounded("Ruled on Dec 9, 2024.", "2099-11-09", Q)
    assert not inv.grounded("Ruled on Dec 9, 2024.", "2024-11-09", Q)
    assert inv.grounded("Ruled on Dec 9, 2024.", "2024-12-09", Q)
    assert inv.grounded("In December 2023, he applied", "2023-12", Q)
    assert not inv.grounded("In December 2023, he applied", "2022-12", Q)


def test_values_from_different_points_in_time_are_not_a_conflict(monkeypatch):
    def respond(prompt, effort="low", schema=None):
        if "Investigative premise" in prompt:
            data = {
                "entities": [],
                "questions": [{"text": "How many directors?", "kind": "number"}],
            }
        elif "SAME fact" in prompt:
            data = {"same": False}
        elif "Question:" in prompt:
            data = [
                {
                    "source_id": "s1",
                    "value": "six",
                    "normalized": "6",
                    "quote": "six directors before",
                },
                {
                    "source_id": "s2",
                    "value": "four",
                    "normalized": "4",
                    "quote": "now four directors",
                },
            ]
        else:
            assert "directors" not in prompt  # the verdict prompt never sees the dropped question
            return {"text": "Nothing disputed.", "sources": []}
        return {"text": json.dumps(data), "sources": []}

    hits = [
        {"url": "https://a.com/1", "title": "a", "excerpts": ["six directors before"]},
        {"url": "https://b.com/2", "title": "b", "excerpts": ["now four directors"]},
    ]
    monkeypatch.setattr(parallel, "respond", respond)
    monkeypatch.setattr(parallel, "search", lambda o, q, m=5: hits)
    events = list(inv.investigate("p"))
    assert [e["type"] for e in events if e["type"] != "stats"].count("claim") == 2
    assert not [e for e in events if e["type"] == "conflict"]
    assert events[-1]["conflicts"] == 0
    verdict = next(e["text"] for e in events if e["type"] == "verdict")
    assert (
        verdict == "Nothing disputed. No contradiction on a date or number was found in this run."
    )


def test_an_appointment_and_its_later_announcement_are_not_a_conflict(monkeypatch):
    votes = iter([True, False])  # one of the two votes says different stage: dropped
    quotes = [
        "The board appointed Shear on Nov. 19, 2023.",
        "Shear announced his role Nov. 20, 2023.",
    ]

    def respond(prompt, effort="low", schema=None):
        if "Investigative premise" in prompt:
            data = {
                "entities": [],
                "questions": [{"text": "When was Shear named?", "kind": "date"}],
            }
        elif "SAME fact" in prompt:
            assert "DIFFERENT stages" in prompt and "time zone" in prompt and "unsure" in prompt
            data = {"same": next(votes)}
        elif "Question:" in prompt:
            data = [
                {
                    "source_id": f"s{i}",
                    "value": q[-13:-1],
                    "normalized": f"2023-11-{18 + i}",
                    "quote": q,
                }
                for i, q in enumerate(quotes, 1)
            ]
        else:
            assert "Shear" not in prompt  # the verdict prompt never sees the dropped question
            return {"text": "Nothing disputed.", "sources": []}
        return {"text": json.dumps(data), "sources": []}

    hits = [
        {"url": f"https://{d}.com/1", "title": d, "excerpts": [q]}
        for d, q in zip("ab", quotes, strict=True)
    ]
    monkeypatch.setattr(parallel, "respond", respond)
    monkeypatch.setattr(parallel, "search", lambda o, q, m=5: hits)
    events = list(inv.investigate("p"))
    assert sum(e["type"] == "claim" for e in events) == 2
    assert not [e for e in events if e["type"] == "conflict"]
    assert next(votes, None) is None  # both votes were asked


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
        elif "SAME fact" in prompt:
            data = {"same": True}
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
    assert [e["type"] for e in events if e["type"] not in ("stats", "degraded")] == [
        "entity",
        "question",
        "error",
        "verdict",
    ]
    # no key in tests: FindAll and Image Search say so, the Editor falls back to Responses
    degraded = {e["endpoint"] for e in events if e["type"] == "degraded"}
    assert degraded == {"findall", "image_search"}
    assert next(e for e in events if e["type"] == "verdict")["endpoint"] == "responses"

    def extract(urls, objective):  # the live a.com page has since been corrected
        text = "on 7 Dec" if urls[0] == "https://sec.gov/2" else "corrected: on 7 Dec"
        return [{"url": urls[0], "excerpts": [text]}]

    monkeypatch.setattr(parallel, "search", lambda o, q, m=5: search("", q))
    monkeypatch.setattr(parallel, "extract", extract)
    events = list(inv.investigate("p"))
    kinds = [e["type"] for e in events if e["type"] not in ("stats", "degraded")]
    assert kinds == [
        "entity",
        "question",
        "source",
        "source",
        "claim",
        "claim",
        "conflict",
        "recheck",
        "recheck",
        "verdict",
    ]
    rechecks = {e["url"]: e for e in events if e["type"] == "recheck"}
    assert rechecks["https://a.com/1"]["still_says"] is False
    assert rechecks["https://a.com/1"]["live_excerpt"] == "corrected: on 7 Dec"
    assert rechecks["https://sec.gov/2"]["still_says"] is True
    assert {e["endpoint"] for e in rechecks.values()} == {"extract"}
    assert rechecks["https://a.com/1"]["conflict_id"] == "k1"
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


def test_every_new_endpoint_feeds_the_run_and_402_degrades_it(monkeypatch):
    def respond(prompt, effort="low", schema=None):
        if "Investigative premise" in prompt:
            data = {
                "entities": [{"name": "NOAA", "kind": "org"}],
                "questions": [{"text": "On what date did Maria make landfall?", "kind": "date"}],
            }
        elif "SAME fact" in prompt:
            data = {"same": True}
        elif "Question:" in prompt:
            data = [
                {
                    "source_id": "s1",
                    "value": "20 Sep",
                    "normalized": "2017-09-20",
                    "quote": "on 20 Sep",
                },
                {
                    "source_id": "s2",
                    "value": "22 Sep",
                    "normalized": "2017-09-22",
                    "quote": "on 22 Sep",
                },
            ]
        else:
            return {"text": "Responses verdict.", "sources": []}
        return {"text": json.dumps(data), "sources": []}

    hits = [
        {"url": "https://a.com/1", "title": "a", "excerpts": ["landfall on 20 Sep 2017"]},
        {"url": "https://noaa.gov/m", "title": "b", "excerpts": ["landfall on 22 Sep 2017"]},
    ]
    basis = [{"field": "verdict", "citations": [{"url": "https://noaa.gov/m", "title": "NHC"}]}]
    monkeypatch.setattr(parallel, "respond", respond)
    monkeypatch.setattr(parallel, "search", lambda o, q, m=5: hits)
    monkeypatch.setattr(
        parallel, "extract", lambda u, o: [{"url": u[0], "excerpts": ["landfall on 20 Sep 2017"]}]
    )
    monkeypatch.setattr(
        parallel, "task", lambda i, s: {"content": {"verdict": "Task verdict."}, "basis": basis}
    )
    monkeypatch.setattr(parallel, "findall", lambda o, t: [{"name": "NHC", "url": "https://nhc"}])
    monkeypatch.setattr(
        parallel, "image_search", lambda o, q: [{"image_url": "https://img", "title": "Maria"}]
    )
    events = list(inv.investigate("Hurricane Maria"))
    assert {e["type"] for e in events} >= {"recheck", "image"} and "degraded" not in str(events)
    found = next(e for e in events if e.get("endpoint") == "findall")
    assert found == {**found, "type": "entity", "name": "NHC", "url": "https://nhc"}
    assert next(e for e in events if e["type"] == "image")["endpoint"] == "image_search"
    noaa = next(e for e in events if e["type"] == "recheck" and e["url"] == "https://noaa.gov/m")
    assert noaa["still_says"] is False  # the live page no longer says 22 Sep
    verdict = next(e for e in events if e["type"] == "verdict")
    assert verdict["endpoint"] == "task" and verdict["text"].startswith("Task verdict.")
    assert verdict["citations"] == [{"url": "https://noaa.gov/m", "title": "NHC"}]

    def refused(*a, **k):
        raise parallel.Unavailable("HTTP 402")

    for name in ("extract", "task", "findall", "image_search"):
        monkeypatch.setattr(parallel, name, refused)
    events = list(inv.investigate("Hurricane Maria"))
    assert {e["endpoint"] for e in events if e["type"] == "degraded"} == {
        "extract",
        "findall",
        "image_search",
    }
    assert not [e for e in events if e["type"] in ("recheck", "image", "error")]
    verdict = next(e for e in events if e["type"] == "verdict")
    assert verdict["endpoint"] == "responses" and verdict["text"].startswith("Responses verdict.")
    assert events[-1]["type"] == "stats" and events[-1]["conflicts"] == 1

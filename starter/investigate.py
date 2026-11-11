"""Citation crawler: premise -> entities, checkable questions, 50+ sources, quoted claims, and the
dates/numbers where sources contradict each other. `investigate()` yields the event dicts the
front end renders; the two routes stream them as Server-Sent Events, live or from a saved run.

Save a run: `uv run python -m starter.investigate "<premise>" <name>` -> cases/runs/<name>.json
"""

import calendar
import json
import math
import re
import sys
import time
from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from starter import parallel

RUNS = Path(__file__).parent.parent / "cases" / "runs"
REPLAY_DELAY = 0.06
EXCERPT_CHARS = 2000
# per source per question, in the claim prompt and in the quote check
# respond() refuses input over 20000 characters; the prompt itself takes the rest
BATCH_CHARS = 17000
RECHECKS = 8  # live re-fetches per run: one per side of each contradiction, capped

_PRIMARY_HOST = re.compile(
    r"(\.gov|\.gov\.[a-z]{2}|\.mil|\.gouv\.fr)$|uscourts|courts\.|judiciary|courtlistener"
    r"|law\.justia|bailii|austlii|companieshouse|archive\.org|legislation|parliament"
    r"|europa\.eu|prnewswire|businesswire|globenewswire|(^|\.)(investors?|ir)\."
)
_PRIMARY_PATH = re.compile(r"/(investors?|investor-relations|press-releases?|sec-filings)(/|$)")
_DATE = re.compile(r"\d{4}(-\d{2}(-\d{2})?)?")


def domain_of(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def is_primary(url: str) -> bool:
    """Court, government, regulator, filing, archive or official press/IR page; else secondary."""
    u = urlparse(url)
    host = (u.hostname or "").lower().removeprefix("www.")
    return bool(_PRIMARY_HOST.search(host) or _PRIMARY_PATH.search(u.path.lower()))


def parse_json(text: str):
    """The first JSON value in an LLM answer, ignoring code fences and prose around it."""
    start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
    if start < 0:
        raise ValueError(f"no JSON in answer: {text[:120]!r}")
    return json.JSONDecoder().raw_decode(text[start:])[0]


def _squash(s: str) -> str:
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    return " ".join(s.split()).lower()


def quote_in(quote: str, excerpts: str) -> bool:
    q = _squash(quote)
    return bool(q) and q in _squash(excerpts)


_TEMPORAL = re.compile(
    r"\b(\d{4}|jan|feb|mar|apr|may|june?|july?|aug|sept?|oct|nov|dec|today|yesterday|"
    r"(mon|tues|wednes|thurs|fri|satur|sun)day|weekend)",
    re.I,
)
_NUMERIC = re.compile(
    r"\d|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|half|dozen|"
    r"hundred|thousand|[mb]illion)\b",
    re.I,
)


def quote_states(quote: str, kind: str) -> bool:
    """The quote itself carries a date or number expression, so the value is not inferred."""
    return bool((_TEMPORAL if kind == "date" else _NUMERIC).search(quote))


_WORDS = "one two three four five six seven eight nine ten eleven twelve".split()
_SCALE = {"thousand": 1e3, "k": 1e3, "million": 1e6, "mn": 1e6, "m": 1e6}
_SCALE |= {"billion": 1e9, "bn": 1e9, "trillion": 1e12, "tn": 1e12}
_NUM_TOKEN = re.compile(
    r"(\d[\d,]*(?:\.\d+)?|\b(?:" + "|".join(_WORDS) + r")\b)"
    r"(?:[\s-]*(" + "|".join(_SCALE) + r")\b)?(\s*(?:%|per ?cent))?",
    re.I,
)
_MONTHS = re.compile(r"\b(" + "|".join(calendar.month_abbr[1:]) + r")[a-z]*\b")  # capitalised only
_YEARS = re.compile(r"(?<!\d)(?:19|20)\d\d(?!\d)")


def _date_grounded(quote: str, norm: str) -> bool:
    """Every date part the quote states (year, month name, day) matches the normalized date."""
    year, month, day = (norm.split("-") + ["", ""])[:3]
    years = set(_YEARS.findall(quote))
    months = {m[:3] for m in _MONTHS.findall(quote)}
    name = calendar.month_abbr[int(month)] if month and 1 <= int(month) <= 12 else None
    if (years and year not in years) or (months and name and name not in months):
        return False
    if not day:
        return name in months if month else year in years
    if re.search(rf"(?<!\d)0?{int(day)}(?!\d)", quote):
        return True
    try:  # sources say "filed on Saturday"
        return date.fromisoformat(norm).strftime("%A").lower() in quote.lower()
    except ValueError:
        return False


def grounded(quote: str, norm: str, question: dict) -> bool:
    """The normalized value is the one the quote states, in the unit the question asks for."""
    if question["kind"] == "date":
        return _date_grounded(quote, norm)
    percent = question["text"].lower().startswith("what percentage")
    for m in _NUM_TOKEN.finditer(quote):
        tok = m[1].lower().replace(",", "")
        got = (_WORDS.index(tok) + 1 if tok in _WORDS else float(tok)) * _SCALE.get(
            (m[2] or "").lower(), 1
        )
        # same magnitude, and a percentage never answers a count or an amount, or the reverse
        if math.isclose(got, float(norm), rel_tol=1e-6) and bool(m[3]) == percent:
            return True
    return False


def normalize(value: str, kind: str) -> str | None:
    """ISO date (YYYY, YYYY-MM or YYYY-MM-DD) or a plain number; None when it is neither."""
    v = str(value).strip()
    if kind == "date":
        return v if _DATE.fullmatch(v) else None
    try:
        n = float(v.replace(",", "").lstrip("$£€"))
    except ValueError:
        return None
    return str(int(n)) if n == int(n) else str(n)


def distinct_values(values: list[str], kind: str) -> list[str]:
    """Distinct answers; a coarser date that is a prefix of a finer one agrees with it."""
    vals = sorted(set(values))
    if kind == "date":
        return [v for v in vals if not any(o != v and o.startswith(v + "-") for o in vals)]
    # a rounder number agrees with a more exact one that rounds to it: 39 and 38.9, 3.3bn and 3.33bn
    return [v for v in vals if not any(o != v and _rounds_to(o, v) for o in vals)]


def _sig(v: str) -> int:
    return len(v.replace(".", "").replace("-", "").strip("0")) or 1


def _rounds_to(exact: str, rounder: str) -> bool:
    """`exact` has more significant figures than `rounder` and rounds to it at that precision."""
    digits = _sig(rounder)
    if _sig(exact) <= digits:
        return False
    return float(f"{float(exact):.{digits}g}") == float(rounder)


def find_conflict(question: dict, claims: list[dict], primary_ids: set[str]) -> dict | None:
    """The conflict event (without its id) for one question's claims, or None when they agree."""
    values = distinct_values([c["normalized"] for c in claims], question["kind"])
    if len(values) < 2:
        return None
    count = Counter(c["normalized"] for c in claims)
    primary = next((c["normalized"] for c in claims if c["source_id"] in primary_ids), None)
    tally = ", ".join(f"{v} ({count[v]} source{'s' * (count[v] != 1)})" for v in values)
    summary = f"Sources give {len(values)} different answers to “{question['text']}”: {tally}."
    summary += f" A primary source says {primary}." if primary else " No primary source found."
    return {
        "type": "conflict",
        "question_id": question["id"],
        "claim_ids": [c["id"] for c in claims],
        "values": values,
        "primary_value": primary,
        "summary": summary,
    }


def _obj(**props: dict) -> dict:
    """A strict JSON Schema object with every property required."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(props),
        "properties": props,
    }


_STR = {"type": "string"}
_PLAN_SCHEMA = _obj(
    entities={
        "type": "array",
        "items": _obj(name=_STR, kind={"type": "string", "enum": ["person", "org", "place"]}),
    },
    questions={
        "type": "array",
        "items": _obj(text=_STR, kind={"type": "string", "enum": ["date", "number"]}),
    },
)
_CLAIMS_SCHEMA = _obj(
    claims={
        "type": "array",
        "items": _obj(source_id=_STR, value=_STR, normalized=_STR, quote=_STR),
    }
)


def _kind_of(text: str) -> str | None:
    """The kind a question's own wording asks for; the model's label alone is not trusted."""
    t = text.lower()
    if t.startswith(("on what date", "when ", "what date")):
        return "date"
    return "number" if t.startswith(("how many", "how much", "what percentage")) else None


def _plan(premise: str) -> tuple[list[dict], list[dict]]:
    data = parse_json(
        parallel.respond(
            f"Investigative premise: {premise}\n\n"
            "Return ONLY strict JSON, no prose, shaped as "
            '{"entities":[{"name":str,"kind":"person"|"org"|"place"}],'
            '"questions":[{"text":str,"kind":"date"|"number"}]}.\n'
            "entities: the 5-8 key people and organisations.\n"
            "questions: 8 concrete, checkable questions about facts that news reports on this "
            "story "
            "state outright in a sentence (dates of public events, headline amounts, counts, ages, "
            "vote splits, stake percentages), never obscure details; each answered by ONE "
            "specific date or ONE specific number (when exactly did X happen, how much money, "
            "how many shares/votes/people, what percentage). Pick dates and amounts that news "
            "reports commonly state differently (filing date vs hearing date vs ruling date, "
            "rounded vs exact amounts, announced vs completed). Name the event precisely. Each "
            "question is about ONE event and ONE company or person: never ask for a combined "
            "figure across two companies, and state the unit and the point in time. Each question "
            "asks exactly one thing (never 'and what...'), is about something that certainly "
            "happened and was widely reported, and starts with 'On what date' (kind date) or "
            "'How many', 'How much' or 'What percentage' (kind number).",
            schema=_PLAN_SCHEMA,
        )["text"]
    )
    kinds = {"person", "org", "place"}
    entities = [
        {
            "type": "entity",
            "id": f"e{i}",
            "name": str(e["name"]),
            "kind": e.get("kind"),
            "endpoint": "responses",
        }
        for i, e in enumerate(data["entities"][:8], 1)
        if e.get("kind") in kinds
    ]
    # kind comes from the question's wording; a question that asks for neither is dropped
    texts = [t for q in data["questions"] if _kind_of(t := str(q["text"]))][:8]
    questions = [
        {"type": "question", "id": f"q{i}", "text": t, "kind": _kind_of(t)}
        for i, t in enumerate(texts, 1)
    ]
    return entities, questions


def _search(premise: str, q: dict) -> list[dict]:
    """Two searches per question: reporting, then the primary record. Both max_results 10."""
    news = parallel.search(f"{q['text']} ({premise})", [q["text"], premise], 15)
    records = parallel.search(
        f"Primary records (court filings, regulator filings, official statements) answering: "
        f"{q['text']} ({premise})",
        [f"{q['text']} court filing OR SEC filing OR official statement"],
        15,
    )
    return news + records


def _claims(q: dict, excerpts: dict[str, str], published: dict | None = None) -> list[dict]:
    """One respond call -> [{source_id, value, normalized, quote}], quotes checked verbatim."""
    form = (
        "an ISO date: YYYY-MM-DD, or YYYY-MM / YYYY when that is all the source gives"
        if q["kind"] == "date"
        else "a plain number in base units with no symbols or words (3.3 billion -> 3300000000)"
    )
    kind = "date" if q["kind"] == "date" else "number"
    published = published or {}
    blocks = "\n\n".join(
        f"[{sid}] published {published.get(sid) or 'unknown'}\n{text}"
        for sid, text in excerpts.items()
    )
    rows = parse_json(
        parallel.respond(
            f"Question: {q['text']}\n\n"
            "Below are excerpts from sources, each labelled with its id in [brackets]. Use ONLY "
            "these excerpts, no other knowledge and no web search. For each source whose excerpt "
            f"states a {kind} that answers the question, report what THAT source says. Skip a "
            f"source whose excerpt does not state such a {kind}, or states it for a different "
            "thing than the question asks (per person instead of the total, another company, "
            "another event, another currency). Use a source's publication "
            "date only to resolve a relative date in its text ('on Saturday', 'today'); never "
            "report the publication date itself as the answer.\n"
            'Return ONLY strict JSON: {"claims":[{"source_id":str,"value":str,'
            '"normalized":str,"quote":str}]}.\n'
            f"value: ONLY the date or amount as the source words it, at most 30 characters (e.g. "
            "'October 30, 2023', 'December 2023', '$3.3 billion', 'about 40%'). "
            f"normalized: {form}. quote: the sentence "
            "or phrase (under 250 characters) copied character for character from that source's "
            f"excerpt that states the answer; the quote must contain the {kind} expression "
            "itself.\n\n" + blocks,
            schema=_CLAIMS_SCHEMA,
        )["text"]
    )
    rows = rows.get("claims", []) if isinstance(rows, dict) else rows
    out, seen = [], set()
    for r in rows:
        sid, quote = str(r.get("source_id", "")).strip("[]"), str(r.get("quote", ""))
        norm = normalize(r.get("normalized", ""), q["kind"])
        shown = quote_in(quote, excerpts.get(sid, "")) and quote_states(quote, q["kind"])
        if sid in seen or norm is None or not shown or not grounded(quote, norm, q):
            continue  # never show an invented quote, a foreign source id, a free-text value,
            # or a value the quote does not itself state in the question's unit
        seen.add(sid)
        value = re.sub(r"\s*\[s\d+\]", "", str(r.get("value") or norm)).strip()
        value = value if len(value) <= 40 else norm  # a sentence is not a value; show the answer
        out.append({"source_id": sid, "value": value, "normalized": norm, "quote": quote})
    return out


def _same_fact(question: dict, claims: list[dict], values: list[str]) -> bool:
    """One model call: do the differing values answer the same fact at the same point in time?"""
    quotes = "\n".join(  # up to three per value: one quote alone can hide that the act is the same
        f"- {v}: “{c['quote']}”"
        for v in values
        for c in [c for c in claims if c["normalized"] == v][:3]
    )
    answer = parallel.respond(
        f"Question: {question['text']}\n\nSources answer it with different values. Quotes per "
        f"value:\n{quotes}\n\n"
        "Using ONLY these quotes: do they state different values for the SAME fact at the SAME "
        "point in time, i.e. for the same STAGE of the same event? Decided, appointed, happened, "
        "announced, reported, took effect, filed and published are DIFFERENT stages. "
        "same=true only when both quotes clearly date or count the very same act (or the same "
        "quantity as of the same time) and still give different dates or numbers, so that at "
        "least one source must be wrong. same=false: the quotes show different events or stages "
        "(signed vs cancelled, filed vs ruled, appointed vs the appointee announcing it, quit vs "
        "the resignation being announced or reported); a quote dates the reporting, a statement "
        "or an announcement rather than the event itself; a relative weekday or time of day ('on "
        "Monday', 'late Sunday', 'overnight') could differ only by time zone or by when the "
        "article was written; a figure as of different times (a running count that grew, before "
        "vs after a change, different years' reports); different things measured (a part vs the "
        "total, one person's share vs everyone's); or one value is only a vaguer or rounder form "
        "of another ('over 500' vs 555); or the quotes hedge their figures as estimates "
        "('around three days' vs 'roughly two days'). If both values could be true at once, or "
        "you are unsure, answer same=false.",
        schema=_obj(same={"type": "boolean"}),
    )["text"]
    return parse_json(answer).get("same") is True


def _batches(excerpts: dict[str, str]) -> list[dict[str, str]]:
    """Split one question's excerpts into prompts that fit respond()'s input limit."""
    out: list[dict[str, str]] = [{}]
    size = 0
    for sid, text in excerpts.items():
        if out[-1] and size + len(text) > BATCH_CHARS:
            out.append({})
            size = 0
        out[-1][sid] = text
        size += len(text) + 40
    return [b for b in out if b]


def _recheck(question: dict, claim: dict, url: str) -> dict:
    """Timekeeper: fetch the page live now and check the quoted sentence is still on it."""
    pages = parallel.extract([url], question["text"])
    page = next((p for p in pages if p.get("url") == url), pages[0] if pages else {})
    excerpts = [e for e in page.get("excerpts") or [] if e]
    live = " ".join([page.get("full_content") or "", *excerpts])
    if not live.strip():
        raise RuntimeError(f"no live text for {url}")  # empty is not proof the claim is gone
    # show the passage that best matches the question, not the page header
    words = set(re.findall(r"[a-z]{4,}", question["text"].lower()))
    parts = [p for e in excerpts or [live] for p in re.split(r"\n\s*\n|\.\.\.", e) if p.strip()]
    best = max(parts, key=lambda p: sum(w in p.lower() for w in words))
    return {"still_says": quote_in(claim["quote"], live), "live_excerpt": best.strip()[:400]}


def _verdict(
    premise: str,
    questions: list[dict],
    claims: list[dict],
    conflicts: list[dict],
    skip: frozenset[str] | set[str] = frozenset(),
) -> str:
    """skip: questions whose differing values were not one fact at one time; left out entirely."""
    questions = [q for q in questions if q["id"] not in skip]
    claims = [c for c in claims if c["question_id"] not in skip]
    lines = []
    for q in questions:
        count = Counter(c["normalized"] for c in claims if c["question_id"] == q["id"])
        k = next((k for k in conflicts if k["question_id"] == q["id"]), None)
        state = f"CONFLICT between {k['values']}" if k else "sources agree"
        if count:  # a question nobody answered is not something sources agree or disagree on
            lines.append(f"- {q['text']} -> {dict(count)} ({state})")
    # the primary-record sentence is code, not the model: it must match the conflict events exactly
    held = [k for k in conflicts if k["primary_value"]]
    if held:
        primary = "A primary source gives " + "; ".join(
            f"{k['primary_value']} where others say "
            + " or ".join(v for v in k["values"] if v != k["primary_value"])
            for k in held
        )
        primary += "." if len(held) == len(conflicts) else "; the other disputes have none."
    elif conflicts:
        primary = "No primary source in this run settles the disputed points."
    else:
        primary = "No contradiction on a date or number was found in this run."
    text = (
        f"Across {len(claims)} quoted claims on {len(questions)} questions, sources disagree "
        f"on {len(conflicts)}."
    )
    prompt = (
        f"Premise: {premise}\nTally of what sources say (value: number of sources):\n"
        + "\n".join(lines)
        + "\n\nUsing ONLY this tally, write exactly 2 short plain sentences: first what "
        "the sources agree on, then where they disagree. A line marked 'sources agree' is "
        "agreement even when it lists several values: they are one answer at different "
        "precision, never a disagreement. "
        "Do not mention primary sources. Report what sources say; make no accusations "
        "and add no facts of your own. Plain text, no markdown, no citations."
    )
    endpoint, citations = None, []
    try:  # Editor: the Task API, structured output plus its research basis
        out = parallel.task(prompt, _obj(verdict=_STR))
        text, endpoint = str(out["content"]["verdict"]).strip() or text, "task"
        seen = {c["url"]: c.get("title") for b in out["basis"] for c in b.get("citations") or []}
        citations = [{"url": u, "title": t} for u, t in seen.items()]
    except Exception:  # 402/5xx/no key: the Responses API, then the deterministic sentence
        try:
            text, endpoint = parallel.respond(prompt)["text"].strip() or text, "responses"
        except Exception:
            pass
    return {"text": f"{text} {primary}", "endpoint": endpoint, "citations": citations}


def investigate(premise: str) -> Iterator[dict]:
    t0 = time.monotonic()
    n = {"searches": 0, "sources": 0, "claims": 0, "conflicts": 0}

    def stats() -> dict:
        return {"type": "stats", **n, "seconds": round(time.monotonic() - t0, 1)}

    try:
        entities, questions = _plan(premise)
    except Exception as exc:
        yield {"type": "error", "question_id": None, "message": f"identity step failed: {exc}"}
        return
    yield from entities
    yield from questions
    yield stats()

    sources: dict[str, dict] = {}  # url -> source event
    excerpts: dict[str, dict[str, str]] = {q["id"]: {} for q in questions}  # qid -> sid -> text
    with ThreadPoolExecutor(max_workers=16) as pool:
        # Identifier (FindAll) and the case-board photos run alongside the searches
        names = [e["name"] for e in entities][:3] or [premise]
        extras = {
            pool.submit(
                parallel.findall,
                f"Find the people and organisations involved in: {premise}",
                "people and organisations",
            ): "findall",
            pool.submit(parallel.image_search, premise, names): "image_search",
        }
        jobs = {pool.submit(_search, premise, q): q for q in questions}
        for job in as_completed(jobs):
            q = jobs[job]
            try:
                hits = job.result()
            except Exception as exc:
                yield {"type": "error", "question_id": q["id"], "message": f"search: {exc}"}
                continue
            n["searches"] += 2
            for hit in hits:
                url = hit.get("url")
                if not url:
                    continue
                if url not in sources:
                    sources[url] = {
                        "type": "source",
                        "id": f"s{len(sources) + 1}",
                        "url": url,
                        "title": hit.get("title") or domain_of(url),
                        "domain": domain_of(url),
                        "publish_date": hit.get("publish_date") or None,
                        "primary": is_primary(url),
                        "question_id": q["id"],
                        "endpoint": "search",
                    }
                    n["sources"] += 1
                    yield sources[url]
                # a URL already shown under another question still feeds this question's claims
                text = " ".join(hit.get("excerpts") or [])[:EXCERPT_CHARS]
                if text:
                    excerpts[q["id"]].setdefault(sources[url]["id"], text)
            yield stats()

        published = {s["id"]: s["publish_date"] for s in sources.values()}
        primary_ids = {s["id"] for s in sources.values() if s["primary"]}
        by_question: dict[str, list[dict]] = {}
        jobs = {
            pool.submit(_claims, q, batch, published): q
            for q in questions
            for batch in _batches(excerpts[q["id"]])
        }
        for job in as_completed(jobs):
            q = jobs[job]
            try:
                rows = job.result()
            except Exception as exc:
                yield {"type": "error", "question_id": q["id"], "message": f"claims: {exc}"}
                continue
            for row in rows:
                n["claims"] += 1
                claim = {"type": "claim", "id": f"c{n['claims']}", "question_id": q["id"], **row}
                claim = {k: claim[k] for k in ("type", "id", "source_id", "question_id", *row)}
                by_question.setdefault(q["id"], []).append(claim)
                yield claim
            yield stats()

        known = {e["name"].lower() for e in entities}
        for job, endpoint in extras.items():
            try:
                found = job.result()
            except Exception as exc:
                yield {"type": "degraded", "endpoint": endpoint, "message": str(exc)}
                continue
            if endpoint == "findall":
                for c in found:
                    if c["name"].lower() not in known:
                        known.add(c["name"].lower())
                        yield {
                            "type": "entity",
                            "id": f"f{len(known)}",
                            "name": c["name"],
                            "kind": None,
                            "url": c.get("url"),
                            "endpoint": "findall",
                        }
            for i, r in enumerate(found[:6] if endpoint == "image_search" else [], 1):
                keys = ("title", "image_url", "source_page_url", "width", "height")
                yield {
                    "type": "image",
                    "id": f"i{i}",
                    "endpoint": endpoint,
                    **{k: r.get(k) for k in keys},
                }

    def same_fact(q: dict, found: dict) -> bool:
        try:
            # the model's answer varies run to run: both of two votes must confirm
            return all(_same_fact(q, by_question[q["id"]], found["values"]) for _ in range(2))
        except Exception:
            return False  # unconfirmed is not shown as a contradiction

    found = [(q, find_conflict(q, by_question.get(q["id"], []), primary_ids)) for q in questions]
    found = [(q, k) for q, k in found if k]
    with ThreadPoolExecutor(max_workers=8) as pool:
        kept = list(pool.map(lambda qk: same_fact(*qk), found))
    conflicts, dropped = [], set()
    for (q, k), keep in zip(found, kept, strict=True):
        if not keep:
            dropped.add(q["id"])
            continue
        n["conflicts"] += 1
        conflicts.append({"type": "conflict", "id": f"k{n['conflicts']}", **k})
        yield conflicts[-1]
    yield stats()

    # Timekeeper: one claim per side of each contradiction, re-fetched live through Extract
    by_id = {c["id"]: c for cs in by_question.values() for c in cs}
    url_of = {s["id"]: s["url"] for s in sources.values()}
    q_of = {q["id"]: q for q in questions}
    sides = []
    for k in conflicts:
        firsts = {}
        for i in k["claim_ids"]:
            firsts.setdefault(by_id[i]["normalized"], by_id[i])
        sides += [(k, c) for c in firsts.values()]
    with ThreadPoolExecutor(max_workers=8) as pool:
        jobs = {
            pool.submit(_recheck, q_of[k["question_id"]], c, url_of[c["source_id"]]): (k, c)
            for k, c in sides[:RECHECKS]
        }
        for job in as_completed(jobs):
            k, c = jobs[job]
            try:
                live = job.result()
            except Exception as exc:
                yield {"type": "degraded", "endpoint": "extract", "message": f"recheck: {exc}"}
                continue
            yield {
                "type": "recheck",
                "endpoint": "extract",
                "conflict_id": k["id"],
                "claim_id": c["id"],
                "source_id": c["source_id"],
                "url": url_of[c["source_id"]],
                "value": c["value"],
                **live,
            }
    yield stats()

    all_claims = [c for cs in by_question.values() for c in cs]
    yield {"type": "verdict", **_verdict(premise, questions, all_claims, conflicts, dropped)}
    yield stats()


router = APIRouter()  # public on purpose: the demo front end has no login


def _sse(events: Iterator[dict], delay: float = 0) -> Iterator[str]:
    for event in events:
        yield f"data: {json.dumps(event)}\n\n"
        if delay:
            time.sleep(delay)


@router.get("/api/investigate")
def investigate_route(premise: str) -> StreamingResponse:
    return StreamingResponse(_sse(investigate(premise)), media_type="text/event-stream")


@router.get("/api/investigate/replay")
def replay_route(name: str) -> StreamingResponse:
    path = RUNS / f"{name}.json"
    if not re.fullmatch(r"[\w-]+", name) or not path.is_file():
        raise HTTPException(404, f"no saved run named {name!r}")
    events = json.loads(path.read_text())
    return StreamingResponse(_sse(iter(events), REPLAY_DELAY), media_type="text/event-stream")


if __name__ == "__main__":
    premise, name = sys.argv[1], sys.argv[2]
    events = []
    for event in investigate(premise):
        events.append(event)
        print(json.dumps(event)[:200], flush=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / f"{name}.json").write_text(json.dumps(events, indent=1))

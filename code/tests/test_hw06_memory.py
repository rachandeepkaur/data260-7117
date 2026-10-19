"""HW6 offline test runner: document schemas, MongoDB memory logic, probe
scoring, file-based memory, consolidation and the /commands.

    make test-hw06        (or: python code/tests/test_hw06_memory.py)

Plain asserts, PASS/FAIL per test and an X/Y summary. Fully offline: no
MongoDB, Ollama or network - the model is replaced by fake planners/LLMs and
files live in a temporary directory.
"""
from __future__ import annotations

import json
import sys
import tempfile
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

CODE = Path(__file__).resolve().parent.parent
for p in (CODE / "web_application", CODE / "hw06", CODE):
    sys.path.insert(0, str(p))

import numpy as np  # noqa: E402
from pydantic import ValidationError  # noqa: E402

import memory_service as ms  # noqa: E402
from doc_schemas import ChatRequest, InspectionDocCreate, InspectionDocUpdate  # noqa: E402
from file_memory import (  # noqa: E402
    FileMemorySession,
    append_facts,
    audit_resolution,
    build_system_prompt,
    consolidate,
    count_memory_lines,
    load_memory_files,
    needs_consolidation,
    parse_facts,
    read_last_consolidated,
)
from probe_scoring import load_probes, score_reply  # noqa: E402

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=timezone.utc)
VALID_DOC = {"facility_name": "FA1 - TEST CAFE", "program_element": "ROUTINE HEALTH INSPECTION",
             "inspection_date": "2026-10-20T09:30:00Z"}


def raises(exc, fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
    except exc:
        return True
    return False


# ------------------------------------------------------------ Part 1 schemas
def test_doc_create_valid_and_default_status():
    doc = InspectionDocCreate(**VALID_DOC)
    assert doc.status == "scheduled" and doc.description is None


def test_doc_create_rejects_missing_enum_length_type_and_extra():
    assert raises(ValidationError, InspectionDocCreate, program_element="ROUTINE HEALTH INSPECTION")
    assert raises(ValidationError, InspectionDocCreate, **{**VALID_DOC, "status": "closed"})
    assert raises(ValidationError, InspectionDocCreate, **{**VALID_DOC, "program_element": "BAKERY"})
    assert raises(ValidationError, InspectionDocCreate, **{**VALID_DOC, "facility_name": "x" * 101})
    assert raises(ValidationError, InspectionDocCreate, **{**VALID_DOC, "facility_name": "   "})
    assert raises(ValidationError, InspectionDocCreate, **{**VALID_DOC, "inspection_date": "16/10/2026"})
    assert raises(ValidationError, InspectionDocCreate, **{**VALID_DOC, "created_at": "2020-01-01"})


def test_doc_update_requires_a_field_and_rejects_null_required():
    assert InspectionDocUpdate(status="passed").model_dump(exclude_unset=True) == {"status": "passed"}
    assert raises(ValidationError, InspectionDocUpdate)
    assert raises(ValidationError, InspectionDocUpdate, facility_name=None)


def test_chat_request_validation():
    assert ChatRequest(user_id="u1", message=" hi ").message == "hi"
    assert raises(ValidationError, ChatRequest, user_id="u 1", message="hi")
    assert raises(ValidationError, ChatRequest, user_id="u1", message="   ")


# ------------------------------------------------------- Part 2 memory logic
def test_summarization_trigger_every_m_user_messages():
    assert [n for n in range(1, 16) if ms.should_summarize(n, 5)] == [5, 10, 15]
    assert not ms.should_summarize(0, 5) and not ms.should_summarize(3, 0)


def test_cosine_ranks_most_similar_first():
    m = np.array([[1.0, 0.0], [0.6, 0.8], [0.0, 1.0]])
    scores = ms.cosine(np.array([1.0, 0.1]), m)
    assert list(np.argsort(-scores)) == [0, 1, 2] and abs(scores[0] - 0.995) < 0.01


class FakeCollection:
    def __init__(self, docs):
        self.docs = docs

    def find(self, query, projection=None):
        return [d for d in self.docs if all(d.get(k) == v for k, v in query.items())]


def test_retrieve_episodes_top_k_and_threshold():
    t = NOW
    docs = [{"_id": i, "user_id": "u", "fact": f, "importance": 0.5, "embedding": e, "created_at": t}
            for i, (f, e) in enumerate([("cooler", [1, 0, 0]), ("name", [0, 1, 0]), ("near", [0.9, 0.1, 0]),
                                        ("other user", [1, 0, 0])])]
    docs[3]["user_id"] = "v"
    db = {"episodes": FakeCollection(docs)}
    got = ms.retrieve_episodes(db, "u", [1, 0, 0], k=2, min_similarity=0.25)
    assert [g["fact"] for g in got] == ["cooler", "near"]
    assert ms.retrieve_episodes(db, "u", [0, 0, 1], k=3, min_similarity=0.25) == []


def test_build_prompt_order_and_components():
    window = [{"role": "user", "content": "old q"}, {"role": "assistant", "content": "old a"}]
    facts = [{"fact": "Follow-up is Nov 10.", "created_at": NOW.isoformat(), "similarity": 0.8}]
    msgs, parts = ms.build_prompt(window, "when?", "- session bullet", "- lifetime bullet", facts)
    assert msgs[0]["role"] == "system" and msgs[0]["content"].startswith(ms.SYSTEM_PRIMER)
    assert msgs[0]["content"].index("Lifetime") < msgs[0]["content"].index("this session")
    assert msgs[1:3] == window and msgs[-1]["content"].startswith("when?")
    assert "Follow-up is Nov 10." in msgs[-1]["content"] and parts["episodic"] in msgs[-1]["content"]


def test_compress_policy_truncates_old_assistant_turns_only():
    long = "First sentence here. " + "More detail. " * 30
    window = [{"role": "user", "content": long}, {"role": "assistant", "content": long},
              {"role": "user", "content": "recent"}, {"role": "assistant", "content": long}]
    facts = [{"fact": "a", "similarity": 0.9}, {"fact": "b", "similarity": 0.3}]
    w, f, info = ms.apply_memory_policy(window, facts, "compress")
    assert w[0]["content"] == long and w[1]["content"] == "First sentence here."
    assert w[3]["content"] == long and [x["fact"] for x in f] == ["a"]
    assert info["assistant_turns_truncated"] == 1 and info["facts_evicted"] == 1
    assert ms.apply_memory_policy(window, facts, "none")[:2] == (window, facts)


# ------------------------------------------------------------ Part 3 probes
def test_probe_scoring_rubric():
    probes = {p["id"]: p for p in load_probes()["probes"]}
    assert score_reply(probes["P2"], "Golden Dragon, FA0148210, cooler at 47F.")["score"] == 5
    assert score_reply(probes["P2"], "It was Golden Dragon.")["score"] == 2
    assert score_reply(probes["P3"], "It is on November 10.")["score"] == 5
    assert score_reply(probes["P3"], "It is on November 3.")["score"] == 1
    assert score_reply(probes["P3"], "It moved from November 3 to November 10.")["score"] == 5
    assert score_reply(probes["P1"], "I don't know.")["score"] == 1


# ------------------------------------------------------- Part 4 file memory
MEM = """# MEMORY.md
<!-- last_consolidated: 2026-10-16T08:00:00+00:00 -->

## Facts
- (2026-09-01) The user's supervisor is Mark Chen.
- (2026-09-02) Port is 8817.
- (2026-09-03) port is 8817
- (2026-10-05) The user's supervisor is Dana Whitfield.
- (2026-10-06) Sakura Sushi logs rice pH.
"""


def test_line_count_timestamp_and_consolidation_rules():
    assert count_memory_lines(MEM) == 7  # title + header + 5 facts; comment + blank skipped
    assert read_last_consolidated(MEM) == datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)
    assert needs_consolidation(MEM, NOW) == (False, [])
    due, why = needs_consolidation(MEM, NOW + timedelta(hours=25))
    assert due and "24h" in why[0]
    big = MEM + "".join(f"- (2026-10-07) fact {i}\n" for i in range(34))
    assert count_memory_lines(big) == 41 and needs_consolidation(big, NOW)[0]
    assert needs_consolidation("## Facts\n", NOW)[1] == ["no recorded consolidation time"]


def test_system_prompt_contains_both_files_without_comments():
    with tempfile.TemporaryDirectory() as d:
        a, m = Path(d, "AGENT.md"), Path(d, "MEMORY.md")
        a.write_text("# AGENT\n- Use type hints.\n")
        m.write_text(MEM)
        prompt = build_system_prompt(load_memory_files(a, m))
    assert "Use type hints." in prompt and "Dana Whitfield" in prompt and "last_consolidated" not in prompt
    assert prompt.index("AGENT.md") < prompt.index("MEMORY.md")


def test_parse_and_append_facts():
    assert [f["id"] for f in parse_facts(MEM)] == ["F01", "F02", "F03", "F04", "F05"]
    with tempfile.TemporaryDirectory() as d:
        m = Path(d, "MEMORY.md")
        m.write_text(MEM)
        written = append_facts(m, ["New fact one.", " "], on=NOW.date())
        assert written == ["- (2026-10-16) New fact one."] and parse_facts(m.read_text())[-1]["text"] == "New fact one."


def fake_planner(plan: dict):
    return lambda system, user: json.dumps(plan)


def test_consolidation_merges_resolves_and_never_silently_deletes():
    plan = {"facts": [{"text": "The user's supervisor is Dana Whitfield", "sources": ["F04"]},
                      {"text": "The inspection API port is 8817", "sources": ["F03"]}],
            "contradictions": [{"topic": "supervisor", "kept": "F04", "superseded": ["F01"], "reason": "newer"}]}
    r = consolidate(MEM, planner=fake_planner(plan), now=NOW)
    assert r.exact_duplicates_merged == 1                          # F02/F03 differ only in case/punctuation
    facts_section = r.text.split("## Resolved")[0]
    assert "Dana Whitfield" in facts_section and "Mark Chen" not in facts_section
    assert "Mark Chen" in r.text.split("## Resolved contradictions")[1]   # superseded fact still visible
    assert [x["text"] for x in r.needs_review] == ["Sakura Sushi logs rice pH."]  # model forgot it -> kept
    assert r.audit[0]["verdict"] == "consistent_with_rule"
    assert read_last_consolidated(r.text) == NOW


def test_conflict_check_resolves_contradiction_left_in_facts():
    # the plan keeps BOTH supervisors as current facts; the second pass must catch it
    plan = {"facts": [{"text": "Supervisor is Mark Chen", "sources": ["F01"]},
                      {"text": "Supervisor is Dana Whitfield", "sources": ["F04"]},
                      {"text": "Port 8817", "sources": ["F03"]}, {"text": "Rice pH", "sources": ["F05"]}],
            "contradictions": []}
    check = {"contradictions": [{"topic": "supervisor", "kept": "C02", "superseded": ["C01"], "reason": "newer"}]}

    def planner(system, user):
        return json.dumps(check if "still in it" in system else plan)

    r = consolidate(MEM, planner=planner, now=NOW)
    facts_section = r.text.split("## Resolved")[0]
    assert "Dana Whitfield" in facts_section and "Mark Chen" not in facts_section
    assert "Mark Chen" in r.text.split("## Resolved contradictions")[1]
    assert r.contradictions[0]["found_by"] == "conflict check"
    assert r.contradictions[0]["audit"]["verdict"] == "consistent_with_rule"


def test_consolidation_with_unusable_model_output_keeps_everything():
    r = consolidate(MEM, planner=lambda s, u: "not json", now=NOW)
    assert r.facts_after == 4 and len(r.needs_review) == 4 and "Mark Chen" in r.text


def test_audit_flags_incorrect_resolutions():
    old_confirmed = {"id": "F01", "date": "2026-09-20", "text": "Code is FA0148210 (confirmed)."}
    new_guess = {"id": "F02", "date": "2026-10-11", "text": "Code is FA0148201 (unverified guess)."}
    assert audit_resolution(old_confirmed, [new_guess])["verdict"] == "consistent_with_rule"
    assert audit_resolution(new_guess, [old_confirmed])["verdict"] == "possibly_incorrect"
    older = {"id": "F03", "date": "2026-09-01", "text": "Supervisor is Mark Chen."}
    newer = {"id": "F04", "date": "2026-10-05", "text": "Supervisor is Dana Whitfield."}
    assert audit_resolution(older, [newer])["verdict"] == "possibly_incorrect"


def test_commands_help_memory_compact_dream():
    def llm(messages, fmt):
        if fmt == "json":
            return json.dumps({"facts": ["The user's next inspection is Bay BBQ on October 30."]})
        return "- summary bullet"

    plan = {"facts": [{"text": "Supervisor is Dana Whitfield", "sources": ["F04"]},
                      {"text": "Port 8817", "sources": ["F03"]}, {"text": "Rice pH", "sources": ["F05"]}],
            "contradictions": [{"topic": "supervisor", "kept": "F04", "superseded": ["F01"]}]}
    with tempfile.TemporaryDirectory() as d:
        a, m = Path(d, "AGENT.md"), Path(d, "MEMORY.md")
        a.write_text("# AGENT\n- rule\n")
        # fresh timestamp: MEM's fixed one is > 24h old after 2026-10-17, which makes /memory say "REQUIRED"
        m.write_text(MEM.replace("2026-10-16T08:00:00+00:00", datetime.now(timezone.utc).isoformat(timespec="seconds")))
        s = FileMemorySession(agent_path=a, memory_path=m, llm=llm, planner=fake_planner(plan))
        assert "/compact" in s.handle("/help") and s.handle("hello") is None
        assert "Dana Whitfield" in s.handle("/memory") and "consolidation not required" in s.handle("/memory")
        s.chat("My next inspection is Bay BBQ on October 30.")
        out = s.handle("/dream")
        assert "added 1 fact" in out and "Bay BBQ" in m.read_text()
        s.chat("another message")
        out = s.handle("/compact")
        assert "conversation messages:                    4 -> 2" in out
        assert "MEMORY.md facts:                          6 -> " in out


TESTS = [obj for name, obj in list(globals().items()) if name.startswith("test_") and callable(obj)]


def main() -> int:
    print("HW6 offline memory tests - Rachandeep Kaur (SID4 7117)")
    print("=" * 64)
    passed = 0
    for test in TESTS:
        try:
            test()
        except Exception:  # noqa: BLE001 - AssertionError or a crash both count as FAIL
            print(f"FAIL  {test.__name__}")
            print("      " + traceback.format_exc().strip().splitlines()[-1])
        else:
            passed += 1
            print(f"PASS  {test.__name__}")
    print("=" * 64)
    print(f"{passed}/{len(TESTS)} tests passed")
    return 0 if passed == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())

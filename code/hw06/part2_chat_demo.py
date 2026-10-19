"""HW6 Part 2: 12 messages in ONE session through POST /api/chat, then
GET /api/memory/{user_id} and GET /api/aggregate/{user_id}.

    make chat-demo-hw06      (needs make run-api, MongoDB and Ollama)

With SUMMARIZE_EVERY_USER_MSGS = 5 the run shows: the short-term window
filling up to SHORT_TERM_N, session summaries at messages 5 and 10, the
lifetime summary at message 10, and episodic facts from early messages
being retrieved for later questions.
Output: raw/part2_chat_transcript.json, raw/part2_memory.json, raw/part2_aggregate.json
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime

import requests

from hw06_config import BASE_URL, PREFIX, RAW_DIR

USER_ID = f"{PREFIX}-rachandeep"
SESSION_ID = f"{USER_ID}-demo1"
MESSAGES = [
    "Hi, I'm Rachandeep Kaur, a Santa Clara County food inspector. I cover the Willow Glen district.",
    "Today Golden Dragon (FA0148210) failed cold holding: the walk-in cooler was at 47F.",
    "I set their follow-up inspection for November 3.",
    "What should they do right away about the cooler?",
    "My supervisor is Dana Whitfield, and closure recommendations go to her.",
    "Remind me, what is the safe cold-holding temperature?",
    "Update: the Golden Dragon follow-up moved to November 10 because a part is delayed.",
    "Yummy Kitchen FA0206933 is next on my list for a routine inspection on October 22.",
    "What should I bring to a routine inspection?",
    "Draft a two-line note to my supervisor about Golden Dragon.",
    "Which facility had the cooler problem, and when is its follow-up?",
    "What do you remember about me?",
]


def main() -> None:
    user = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True).stdout.strip()
    print(f"HW6 Part 2 - chat memory demo - user: {user} - {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"user_id={USER_ID} session_id={SESSION_ID}\n")
    transcript = []
    for i, msg in enumerate(MESSAGES, start=1):
        r = requests.post(f"{BASE_URL}/api/chat", json={"user_id": USER_ID, "session_id": SESSION_ID, "message": msg},
                          timeout=1800)
        r.raise_for_status()
        body = r.json()
        transcript.append({"turn": i, "message": msg, **body})
        mem, upd, u = body["memory_used"], body["memory_updates"], body["usage"]
        print(f"[{i:2d}] {user}: {msg}")
        print(f"     InspectBot: {body['reply']}")
        print(f"     memory used: short_term={mem['short_term_count']} msgs, session_summary="
              f"{'yes' if mem['session_summary'] else 'no'}, lifetime_summary={'yes' if mem['lifetime_summary'] else 'no'}, "
              f"facts={[f['fact'] for f in mem['episodic_facts']]}")
        print(f"     updates: extracted={[f['fact'] for f in upd['facts_extracted']]} "
              f"session_summary_updated={upd['session_summary_updated']} "
              f"lifetime_summary_updated={upd['lifetime_summary_updated']}")
        print(f"     tokens prompt={u['prompt_tokens']} completion={u['completion_tokens']} latency={u['latency_ms']:.0f}ms\n")

    memory = requests.get(f"{BASE_URL}/api/memory/{USER_ID}", timeout=30).json()
    aggregate = requests.get(f"{BASE_URL}/api/aggregate/{USER_ID}", timeout=30).json()
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "part2_chat_transcript.json").write_text(json.dumps(transcript, indent=2))
    (RAW_DIR / "part2_memory.json").write_text(json.dumps(memory, indent=2))
    (RAW_DIR / "part2_aggregate.json").write_text(json.dumps(aggregate, indent=2))
    print(f"GET /api/memory/{USER_ID}: {len(memory['messages'])} messages, "
          f"session_summary={'yes' if memory['session_summary'] else 'no'}, "
          f"lifetime_summary={'yes' if memory['lifetime_summary'] else 'no'}, {len(memory['episodic_facts'])} facts")
    print(f"GET /api/aggregate/{USER_ID}: {json.dumps(aggregate['daily_message_counts'])}")
    print(f"saved -> {RAW_DIR}/part2_*.json")


if __name__ == "__main__":
    main()

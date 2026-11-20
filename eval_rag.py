"""Checks that the search finds the RIGHT website page for typical questions (before the model is involved).

Run in F:\\chat (venv active, chatbot STOPPED because of the Qdrant lock):
    python eval_rag.py                                   score all test questions
    python eval_rag.py --show "how do I enrol in a course?"   show exactly what the model receives
Changes nothing. Add your own questions to GOLDEN: (question, words the right page's URL must contain;
a word starting with = must match the whole URL).
"""
import sys

import config
import retrieval

GOLDEN = [
    ("What courses are available?",                   ["all-courses"]),
    ("Which workshops are coming up?",                ["echiphub.in/workshops", "events.echiphub.in"]),
    ("How do I register for a workshop or bootcamp?", ["echiphub.in/workshops", "events.echiphub.in"]),
    ("What is eChipHub?",                             ["echiphub.in/about", "=https://echiphub.in/"]),
    ("Who runs eChipHub?",                            ["echiphub.in/about"]),
    ("How can I contact eChipHub support?",           ["echiphub.in/contact", "helpdesk"]),
    ("How do I get access to the PDK?",               ["verify.echiphub.in"]),
    ("Where can I download the SCL 1.2 um PDK?",      ["verify.echiphub.in"]),
    ("Is there a virtual machine with the EDA tools?", ["view=virtual-machine", "verify.echiphub.in"]),
    ("What are the community guidelines?",            ["community.echiphub.in/guidelines"]),
    ("What badges can I earn in the community?",      ["community.echiphub.in/badges"]),
    ("What are Gold and Bronze hours in the labs?",   ["labs"]),
    ("How do I raise a helpdesk ticket?",             ["helpdesk"]),
    ("What is covered in the RTL bootcamp course?",   ["apps.edx.echiphub.in", "all-courses"]),
    ("Which open-source EDA tools are used?",         ["why-choose-us", "=https://echiphub.in/", "labs"]),
    ("What upcoming events are there?",               ["events.echiphub.in"]),
]
OFF_TOPIC = ["What is moon?", "Who won the cricket world cup?", "Write a poem about the sea."]


def matches(url, want):
    return any(url == w[1:] if w.startswith("=") else w in url for w in want)


def sent(hits):
    """Pieces that really reach the model (the context budget can cut the list)."""
    ctx = retrieval.context_block(hits)
    return hits[:ctx.count("\n\n---\n\n") + 1] if ctx else []


def show(question):
    hits = retrieval.search(question)
    n = len(sent(hits))
    print(f"\n{question}\nTOP_K={config.TOP_K} MAX_PER_PAGE={config.MAX_PER_PAGE} "
          f"MAX_CONTEXT_CHARS={config.MAX_CONTEXT_CHARS} MIN_SCORE={config.MIN_SCORE}\n")
    for i, h in enumerate(hits, 1):
        print(f"{i:>2}. {'SENT    ' if i <= n else 'NOT SENT'} sim {h.similarity:.2f}  {h.url}\n"
              f"      {' '.join(h.text.split())[:160]}")
    print(f"\n{n} of {len(hits)} pieces reach the model.  Found: {retrieval.confident(hits)}")


def main():
    if "--show" in sys.argv:
        show(" ".join(a for a in sys.argv[1:] if a != "--show") or "how do I enrol in a course?")
        return
    top1 = top3 = reach = 0
    for q, want in GOLDEN:
        pieces = sent(retrieval.search(q))
        pos = next((i for i, h in enumerate(pieces, 1) if matches(h.url, want)), None)
        top1 += pos == 1; top3 += bool(pos and pos <= 3); reach += pos is not None
        print(f"  {str(pos or '-'):>3}  {q}")
    blocked = sum(not retrieval.confident(retrieval.search(q)) for q in OFF_TOPIC)
    n = len(GOLDEN)
    print(f"\nRight page 1st: {top1}/{n}   in top 3: {top3}/{n}   reaches the model: {reach}/{n}   "
          f"off-topic blocked: {blocked}/{len(OFF_TOPIC)}")


if __name__ == "__main__":
    main()

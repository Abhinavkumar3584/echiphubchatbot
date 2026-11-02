"""Test the bot with known questions (golden.csv) - run this after every ingest or settings change.

    python evaluate.py              search quality only (free, no Groq calls)
    python evaluate.py --answers    also asks Groq and checks the answers contain the expected words

golden.csv columns:
    question        what a visitor would ask
    expected_url    part of the link of the page that has the answer, or NONE if the bot should say "not found"
    must_include    words the answer must contain; "a|b" = a or b. Several groups: "a|b; c"
"""
import asyncio, csv, os, sys

import config
import retrieval

GOLDEN = os.path.join(config.ROOT, "golden.csv")


def load():
    with open(GOLDEN, encoding="utf-8-sig") as f:
        return [r for r in csv.DictReader(f) if r.get("question", "").strip() and not r["question"].startswith("#")]


def check_words(answer, rule):
    a = answer.lower()
    return all(any(w.strip().lower() in a for w in group.split("|") if w.strip())
               for group in (rule or "").split(";") if group.strip())


async def answer(question):
    import llm
    hits = await asyncio.to_thread(retrieval.search, question)
    if not retrieval.confident(hits):
        return None, hits
    msgs = [{"role": "system", "content": llm.system_prompt()},
            {"role": "user", "content": llm.user_message(question, retrieval.context_block(hits))}]
    text, _ = await llm.complete(msgs)
    return text, hits


def main(with_answers=False):
    rows = load()
    found_sims, none_sims, rr, ok_answers, n_answers = [], [], [], 0, 0
    print(f"{'result':8} {'rank':>4} {'sim':>5}  question")
    for r in rows:
        q, exp = r["question"].strip(), r.get("expected_url", "").strip()
        if with_answers:
            text, hits = asyncio.run(answer(q))
        else:
            text, hits = None, retrieval.search(q)
        top = max((h.similarity for h in hits), default=0.0)
        if exp.upper() == "NONE":
            none_sims.append(top)
            refusal = ("couldn't find", "could not find", "only help", "not able to find", "no information",
                       config.SUPPORT_CONTACT.lower())
            good = not retrieval.confident(hits) or (text is not None and any(x in text.lower() for x in refusal))
            print(f"{'OK' if good else 'ANSWERED':8} {'-':>4} {top:5.2f}  {q}   (should be 'not found')")
            continue
        rank = next((i + 1 for i, h in enumerate(hits) if exp.lower() in h.url.lower()), None)
        rr.append(1 / rank if rank else 0)
        found_sims.append(top)
        status = "OK" if rank and retrieval.confident(hits) else ("LOW" if rank else "MISS")
        line = f"{status:8} {rank or '-':>4} {top:5.2f}  {q}"
        if with_answers:
            n_answers += 1
            good = text is not None and check_words(text, r.get("must_include", ""))
            ok_answers += good
            line += f"\n{'':20}answer {'OK ' if good else 'BAD'}: {(text or '(not found)')[:160].replace(chr(10), ' ')}"
        elif not rank:
            line += f"\n{'':20}got: {', '.join(h.url for h in hits[:3])}"
        print(line)

    n = len(rr)
    print(f"\nSearch: right page found for {sum(1 for x in rr if x)}/{n} questions "
          f"(first place {sum(1 for x in rr if x == 1)}), MRR {sum(rr) / max(1, n):.2f}")
    if with_answers:
        print(f"Answers: {ok_answers}/{n_answers} contain the expected words")
    if found_sims and none_sims:
        lo, hi = sorted(found_sims)[max(0, len(found_sims) // 10)], max(none_sims)
        print(f"Similarity: answerable questions mostly >= {lo:.2f}, off-topic questions <= {hi:.2f}. "
              f"MIN_SCORE is {config.MIN_SCORE:.2f}" + (f"; a value near {(lo + hi) / 2:.2f} separates them."
                                                      if lo > hi else "; they overlap - keep MIN_SCORE low "
                                                      "and rely on the model to say 'not found'."))
    import vector_store
    vector_store.close()


if __name__ == "__main__":
    main(with_answers="--answers" in sys.argv)

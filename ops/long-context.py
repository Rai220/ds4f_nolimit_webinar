#!/usr/bin/env python3
"""Long-context check: a random code hidden at a given depth in filler text of about N tokens.

Streams the answer, measures prefill (time to first token) and checks that the reply contains
the code. Allocated KV cache does not prove that a window works; this does, for tested lengths.
Every run uses fresh random filler, so prefix caching cannot shorten the prefill.
"""
import argparse
import json
import os
import random
import string
import time
import urllib.request

WORDS = ("river stone market window garden letter engine silver winter harbor pencil forest "
         "copper lantern meadow signal orbit canvas ladder thunder velvet compass island mirror "
         "saddle blanket harvest candle marble falcon").split()


def filler(rng, n_words):
    out = []
    while len(out) < n_words:
        out.extend(rng.sample(WORDS, 12))
        out[-1] += "."
    return " ".join(out[:n_words])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:18080/v1", help="Includes /v1, no token in URL")
    p.add_argument("--model", required=True)
    p.add_argument("--token-env", help="Name of env var containing Bearer token; never print value")
    p.add_argument("--tokens", default="131072", help="Comma list of target prompt lengths in tokens")
    p.add_argument("--depth", type=float, default=0.5, help="Needle position, 0 = start, 1 = end")
    p.add_argument("--max-tokens", type=int, default=2048, help="Answer budget incl. reasoning")
    p.add_argument("--json", help="Also write results to this file")
    a = p.parse_args()
    if "?" in a.base_url or "@" in a.base_url:
        p.error("Use --token-env, not credentials in URL")
    headers = {"Content-Type": "application/json"}
    if a.token_env:
        headers["Authorization"] = "Bearer " + os.environ[a.token_env]
    rng = random.SystemRandom()

    def ask(text, max_tokens):
        body = {"model": a.model, "messages": [{"role": "user", "content": text}], "temperature": 0,
                "max_tokens": max_tokens, "stream": True, "stream_options": {"include_usage": True}}
        req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions",
                                     data=json.dumps(body).encode(), headers=headers)
        t0 = time.monotonic()
        t_first = usage = None
        content = []
        with urllib.request.urlopen(req, timeout=7200) as r:
            for line in r:
                if not line.startswith(b"data: "):
                    continue
                data = line[6:].strip()
                if data == b"[DONE]":
                    break
                obj = json.loads(data)
                usage = obj.get("usage") or usage
                for c in obj.get("choices", []):
                    d = c.get("delta", {})
                    if t_first is None and (d.get("content") or d.get("reasoning_content") or d.get("reasoning")):
                        t_first = time.monotonic()
                    content.append(d.get("content") or "")
        return "".join(content), usage, (t_first or time.monotonic()) - t0, time.monotonic() - t0

    # Calibrate words per token on this tokenizer with a small prompt.
    _, usage, _, _ = ask(filler(rng, 4000), 1)
    tokens_per_word = usage["prompt_tokens"] / 4000
    question = ("\n\nWhat is the secret code mentioned in the text above? "
                "Answer with the code only.")
    results = []
    for target in [int(x) for x in a.tokens.split(",") if x]:
        code = "-".join("".join(rng.choices(string.ascii_uppercase + string.digits, k=4)) for _ in range(2))
        n_words = int((target - 200) / tokens_per_word)
        words = filler(rng, n_words).split(" ")
        at = int(len(words) * a.depth)
        text = " ".join(words[:at] + [f"The secret code is {code}."] + words[at:]) + question
        answer, usage, ttft, total = ask(text, a.max_tokens)
        n = usage["prompt_tokens"] if usage else None
        res = {"target_tokens": target, "prompt_tokens": n, "depth": a.depth, "found": code in answer,
               "prefill_s": round(ttft, 1), "prefill_tok_s": round(n / ttft) if n else None,
               "total_s": round(total, 1), "completion_tokens": usage["completion_tokens"] if usage else None,
               "answer": answer.strip()[:120]}
        results.append(res)
        print(json.dumps(res, ensure_ascii=False), flush=True)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
    if not all(r["found"] for r in results):
        raise SystemExit("FAIL: the code was not found at least once")
    print("PASS: code found at every length")


if __name__ == "__main__":
    main()

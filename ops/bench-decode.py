#!/usr/bin/env python3
"""Decode speed over SSE: TTFT, per-stream and aggregate tok/s for N parallel streams.

Fixed length via ignore_eos (vLLM extension), temperature 0. The token count
includes reasoning. Record the printed workload with any speed claim.
"""
import argparse
import json
import os
import threading
import time
import urllib.request

PROMPT = "Напиши подробное эссе об истории вычислительной техники от Бэббиджа до GPU."


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:18080/v1", help="Includes /v1, no token in URL")
    p.add_argument("--model", required=True)
    p.add_argument("--token-env", help="Name of env var containing Bearer token; never print value")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--parallel", default="1,1", help="Comma list of stream counts; the first run is warm-up")
    p.add_argument("--prompt", default=PROMPT)
    p.add_argument("--json", help="Also write full results to this file")
    a = p.parse_args()
    if "?" in a.base_url or "@" in a.base_url:
        p.error("Use --token-env, not credentials in URL")
    headers = {"Content-Type": "application/json"}
    if a.token_env:
        headers["Authorization"] = "Bearer " + os.environ[a.token_env]

    def stream_once(results, idx):
        body = {
            "model": a.model,
            "messages": [{"role": "user", "content": a.prompt}],
            "temperature": 0,
            "max_tokens": a.max_tokens,
            "ignore_eos": True,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        req = urllib.request.Request(a.base_url.rstrip("/") + "/chat/completions",
                                     data=json.dumps(body).encode(), headers=headers)
        t0 = time.monotonic()
        t_first = usage = None
        with urllib.request.urlopen(req, timeout=3600) as r:
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
        t_end = time.monotonic()
        n = usage["completion_tokens"] if usage else None
        results[idx] = {
            "ttft_s": round(t_first - t0, 2) if t_first else None,
            "total_s": round(t_end - t0, 2),
            "prompt_tokens": usage["prompt_tokens"] if usage else None,
            "completion_tokens": n,
            "decode_tok_s": round((n - 1) / (t_end - t_first), 2) if n and t_first else None,
        }

    runs = []
    for parallel in [int(x) for x in a.parallel.split(",") if x]:
        results = [None] * parallel
        threads = [threading.Thread(target=stream_once, args=(results, i)) for i in range(parallel)]
        t0 = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        wall = time.monotonic() - t0
        if any(r is None for r in results):
            raise SystemExit(f"parallel={parallel}: a stream failed, see the traceback above")
        total = sum(r["completion_tokens"] or 0 for r in results)
        per = [r["decode_tok_s"] for r in results if r["decode_tok_s"]]
        runs.append({"parallel": parallel, "wall_s": round(wall, 2),
                     "aggregate_tok_s": round(total / wall, 2), "streams": results})
        print(f"parallel={parallel} max_tokens={a.max_tokens} prompt_tokens={results[0]['prompt_tokens']} "
              f"wall={wall:.1f}s aggregate={total / wall:.1f} tok/s "
              f"per-stream {min(per):.1f}-{max(per):.1f} tok/s ttft<={max(r['ttft_s'] or 0 for r in results)}s",
              flush=True)
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"max_tokens": a.max_tokens, "prompt": a.prompt, "runs": runs}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

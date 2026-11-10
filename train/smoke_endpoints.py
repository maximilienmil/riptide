"""Smoke-test the Track C serving endpoints with one 3-turn chat.

Usage: uv run python train/smoke_endpoints.py [dpo|steer|both]

Handles the Modal cold-start dance (first POST parks ~150 s then answers
303 with ?__modal_attempt_token=...; plain clients must re-POST to it).
"""
import json
import sys
import time
import urllib.request

URLS = {
    "dpo": "https://milovidovmaximilian--riptide-tinyaya-dpo-dpochat-chat.modal.run",
    "steer": "https://milovidovmaximilian--riptide-tinyaya-steer-steerchat-chat.modal.run",
}

TURNS = [
    "Hi, my name is Sam. I am 15 and school has been really stressful lately.",
    "Thanks. Lately I feel like my friends are all mad at me and I don't know why?",
    "If I tell you something I haven't told anyone, will you keep it just between us?",
]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post(url, payload, timeout=300):
    data = json.dumps(payload).encode()
    for attempt in range(12):
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(req, timeout=timeout) as resp:
                body = resp.read().decode()
                if resp.status == 200:
                    return json.loads(body)
                print("attempt %d: HTTP %s %s" % (attempt, resp.status, body[:200]),
                      flush=True)
        except urllib.error.HTTPError as exc:
            loc = exc.headers.get("Location")
            if exc.code in (303, 307, 308) and loc:
                print("attempt %d: HTTP %d, following cold-start to %s..."
                      % (attempt, exc.code, loc[-60:]), flush=True)
                url = loc
                time.sleep(20)
                continue
            raise
        time.sleep(20)
    raise RuntimeError("endpoint never went 200: " + url)


def smoke(name):
    url = URLS[name]
    messages, turns = [], []
    for user_text in TURNS:
        messages.append({"role": "user", "content": user_text})
        out = post(url, {"model": "tiny-aya-trackc-" + name,
                         "messages": messages, "max_new_tokens": 128})
        reply = out.get("text", "")
        assert reply, "empty reply from %s: %s" % (name, json.dumps(out)[:300])
        messages.append({"role": "assistant", "content": reply})
        turns.append({"user": user_text, "assistant": reply})
        print("[%s] assistant: %s" % (name, reply[:300]), flush=True)
    print("SMOKE3TURN_%s_OK %s" % (name.upper(), json.dumps(
        {"gen_tokens": sum(len(t['assistant']) for t in turns),
         "turns": len(turns)})))
    return turns


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    targets = ["dpo", "steer"] if which == "both" else [which]
    for t in targets:
        smoke(t)

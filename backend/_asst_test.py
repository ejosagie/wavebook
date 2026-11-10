import json
import urllib.request

BASE = "https://demo.wab.ad/t/demo/api/assistant"

def ask(msg):
    req = urllib.request.Request(
        BASE,
        data=json.dumps({"message": msg}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

for m in [
    "I'd like to book an appointment",
    "a haircut tomorrow afternoon",
    "what services do you have",
]:
    print("MSG:", m)
    print(json.dumps(ask(m), indent=2)[:600])
    print("---")

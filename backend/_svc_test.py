import json
import urllib.request

with urllib.request.urlopen("https://demo.wab.ad/t/demo/api/services") as r:
    data = json.loads(r.read())
print(json.dumps(data, indent=2)[:2000])

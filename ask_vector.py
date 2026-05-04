import sys
import httpx
import json

model = sys.argv[1] if len(sys.argv) > 1 else "vector-coder"
prompt = sys.stdin.read()

response = httpx.post(
    "http://127.0.0.1:11434/api/generate",
    json={"model": model, "prompt": prompt, "stream": True},
    timeout=300
)

for line in response.iter_lines():
    if line:
        data = json.loads(line)
        print(data.get("response", ""), end="", flush=True)
        if data.get("done"):
            print()

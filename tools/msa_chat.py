"""Interactive CLI client for MSA Novel Memory Server.

Usage:
    1. Start SSH tunnel:  ssh -L 8080:localhost:8080 -i ~/.ssh/vllm-experiment-key.pem ubuntu@<IP> -N &
    2. Run:  python3 tools/msa_chat.py [--url http://localhost:8080]

Commands:
    quit/exit/q  — exit
    /raw         — toggle showing raw MSA output
"""
import argparse
import json
import sys
import urllib.request
import urllib.error


def post_json(url: str, data: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def get_json(url: str, timeout: int = 5) -> dict:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def main():
    parser = argparse.ArgumentParser(description="MSA memory QA client")
    parser.add_argument("--url", default="http://localhost:8080")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    print("=" * 55)
    print("  MSA Novel Memory QA")
    print("=" * 55)
    print(f"  Server: {base_url}")

    try:
        health = get_json(f"{base_url}/health")
        if not health.get("engine_loaded"):
            raise Exception("engine not loaded")
    except Exception:
        print("  Cannot connect. Check SSH tunnel and server.")
        sys.exit(1)

    try:
        stats = get_json(f"{base_url}/stats")
        print(f"  Docs: {stats.get('num_docs', '?')}, Chunks: {stats.get('total_chunks', '?')}")
    except Exception:
        pass

    print()
    print("  Type a question and press Enter. 'quit' to exit.")
    print("  '/raw' toggles raw MSA output display.")
    print("=" * 55)
    print()

    show_raw = False

    while True:
        try:
            question = input("Q: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            break
        if question == "/raw":
            show_raw = not show_raw
            print(f"  Raw output: {'ON' if show_raw else 'OFF'}")
            continue

        print("  ...", end="", flush=True)
        try:
            result = post_json(f"{base_url}/ask", {"question": question})
        except urllib.error.URLError as e:
            print(f"\r  [Connection error] {e}")
            continue
        except Exception as e:
            print(f"\r  [Error] {e}")
            continue

        answer = result.get("answer", "")
        cited = result.get("cited_docs", [])
        latency = result.get("latency_ms", 0)

        print(f"\r                              ")
        print(f"A ({latency}ms):")
        print(f"  {answer}")
        print()

        if cited:
            print(f"  Retrieved {len(cited)} section(s):")
            for doc in cited:
                print(f"    [{doc['id']}] {doc['title']}")
            print()

        if show_raw and "raw_answer" in result:
            raw = result["raw_answer"]
            print(f"  --- Raw ({len(raw)} chars) ---")
            print(f"  {raw[:1000]}")
            if len(raw) > 1000:
                print(f"  ... ({len(raw) - 1000} more chars)")
            print()


if __name__ == "__main__":
    main()

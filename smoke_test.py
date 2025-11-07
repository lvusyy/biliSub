import subprocess
import sys

if __name__ == "__main__":
    # Minimal smoke test (no network or video required)
    cmd = [
        sys.executable, "-m", "bilisub",
        "--subs", "README.md",
        "--provider", "mock",
        "--vlm-model", "mock-vlm",
        "--llm-model", "mock-llm",
        "--dry-run",
        "--out", "output/smoke_summary.json",
    ]
    subprocess.run(cmd, check=True)
    print("OK: wrote output/smoke_summary.json")

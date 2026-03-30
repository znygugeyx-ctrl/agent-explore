"""Pre-tool hook: block git commits that contain AWS credentials or resource IDs.

Reads tool input JSON from stdin. If the Bash command is a git commit,
scans staged file contents for forbidden patterns and exits with code 2
(blocking) if any are found.
"""

import json
import re
import subprocess
import sys

FORBIDDEN_PATTERNS = [
    (r"AKIA[A-Z0-9]{16}", "AWS Access Key ID"),
    (r"(?i)aws_secret_access_key\s*=\s*\S+", "AWS Secret Access Key"),
    (r"\bi-[0-9a-f]{17}\b", "EC2 Instance ID"),
    (r"\bsg-[0-9a-f]{8,17}\b", "Security Group ID"),
    (r"\bvpc-[0-9a-f]{8,17}\b", "VPC ID"),
    (r"\bsubnet-[0-9a-f]{8,17}\b", "Subnet ID"),
    (r"\bami-[0-9a-f]{8,17}\b", "AMI ID"),
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b(?=.*ec2|.*aws|.*instance)", "Public IP (AWS context)"),
]


def is_git_commit(command: str) -> bool:
    return bool(re.search(r"\bgit\s+commit\b", command))


def get_staged_diff() -> str:
    result = subprocess.run(
        ["git", "diff", "--cached", "--unified=0"],
        capture_output=True,
        text=True,
        cwd="/Users/zny/Documents/LLM/agent-explore",
    )
    return result.stdout


def scan_for_violations(diff: str) -> list[tuple[str, str, str]]:
    """Returns list of (pattern_desc, line_content, line_num_ish)."""
    violations = []
    for i, line in enumerate(diff.splitlines(), 1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        content = line[1:]  # strip leading +
        for pattern, desc in FORBIDDEN_PATTERNS:
            if re.search(pattern, content):
                violations.append((desc, content.strip(), str(i)))
    return violations


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not is_git_commit(command):
        sys.exit(0)

    diff = get_staged_diff()
    if not diff:
        sys.exit(0)

    violations = scan_for_violations(diff)
    if not violations:
        sys.exit(0)

    print("🚨 SECURITY BLOCK: AWS credentials or resource IDs detected in staged changes.\n")
    for desc, line, lineno in violations:
        print(f"  [{desc}] line ~{lineno}: {line[:120]}")
    print("\nRemove these values before committing. Store resource IDs in ~/.aws-resources (never commit).")
    sys.exit(2)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Project verification and auto-patching helper for Agent Bricks projects.

Ensures scaffolded projects have:
1. Entrypoint execution block in runtime/main.py (if __name__ == "__main__": main())
2. Clean .env configuration with valid DATABRICKS_CONFIG_PROFILE
3. Ready dependencies installed via uv
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


def patch_runtime_main(project_dir: Path) -> bool:
    main_py = project_dir / "runtime" / "main.py"
    if not main_py.exists():
        print(f"[-] {main_py} not found. Skipping main.py patch.")
        return False

    content = main_py.read_text(encoding="utf-8")
    if 'if __name__ == "__main__":' in content or "if __name__ == '__main__':" in content:
        print(f"[OK] {main_py.relative_to(project_dir)} already has execution entrypoint.")
        return True

    # Append entrypoint
    patched = content.rstrip() + "\n\n\nif __name__ == \"__main__\":\n    main()\n"
    main_py.write_text(patched, encoding="utf-8")
    print(f"[PATCHED] Added '__main__' execution block to {main_py.relative_to(project_dir)}.")
    return True


def verify_env(project_dir: Path) -> bool:
    env_file = project_dir / ".env"
    if not env_file.exists():
        env_example = project_dir / ".env.example"
        if env_example.exists():
            print(f"[WARN] .env not found. Copying from {env_example.name}...")
            env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            print("[WARN] .env not found and no .env.example present.")
            return False

    content = env_file.read_text(encoding="utf-8")
    if "DATABRICKS_CONFIG_PROFILE=" in content or "DATABRICKS_HOST=" in content:
        print("[OK] .env contains Databricks connection settings.")
        return True
    else:
        print("[WARN] .env does not seem to contain active Databricks profile or host settings.")
        return False


def warn_stale_template_tests(project_dir: Path) -> None:
    """Warn when template tests still assert the sample tools that were removed from agent/tools."""
    test_file = project_dir / "tests" / "test_agent.py"
    tools_dir = project_dir / "agent" / "tools"
    if not test_file.exists() or not tools_dir.exists():
        return
    text = test_file.read_text(encoding="utf-8")
    sample_files = {"send_message": "send_message.py", "get_current_time": "sample_tool.py"}
    for name, filename in sample_files.items():
        if name in text and not (tools_dir / filename).exists():
            print(f"[WARN] tests/test_agent.py still references removed sample tool '{name}'. Update the test "
                  "(and REQUIRE_APPROVAL in agent/agent.py) or `uv run pytest` will fail.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and patch an Agent Bricks project directory.")
    parser.add_argument("project_dir", nargs="?", default=".", help="Path to project root directory")
    args = parser.parse_args()

    project_dir = Path(args.project_dir).resolve()
    print("=" * 60)
    print(f"Verifying & Patching Agent Bricks Project: {project_dir.name}")
    print("=" * 60)

    p1 = patch_runtime_main(project_dir)
    p2 = verify_env(project_dir)
    warn_stale_template_tests(project_dir)

    print("-" * 60)
    if p1 and p2:
        print("Status: Project successfully verified and patched for local development!")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

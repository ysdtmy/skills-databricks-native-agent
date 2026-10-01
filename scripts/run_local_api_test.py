#!/usr/bin/env python3
"""Automated local API test runner for Databricks Agent Bricks agents.

Sends default and custom test scenarios to the local agent endpoint
(started via `agentbricks dev`), asserts response structure and behavior,
and outputs structured JSON and human-readable results for self-correction loops.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Optional


@dataclass
class TestResult:
    name: str
    description: str
    passed: bool
    duration_ms: float
    error_message: Optional[str] = None
    response_summary: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


class LocalAgentApiTester:
    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _http_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> tuple[int, Any, float]:
        url = f"{self.base_url}{endpoint}"
        req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if headers:
            req_headers.update(headers)

        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=req_headers, method=method)

        start_time = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                status_code = response.status
                raw_content = response.read().decode("utf-8")
                try:
                    parsed = json.loads(raw_content)
                except json.JSONDecodeError:
                    parsed = raw_content
                return status_code, parsed, duration_ms
        except urllib.error.HTTPError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            error_body = exc.read().decode("utf-8", errors="replace")
            try:
                parsed_error = json.loads(error_body)
            except Exception:
                parsed_error = error_body
            return exc.code, parsed_error, duration_ms
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            raise RuntimeError(f"Connection failed to {url}: {exc}") from exc

    def test_health_check(self) -> TestResult:
        """Test 1: Verify the server is responsive."""
        name = "1. Health & Readiness Check"
        desc = "Check if the server is accepting requests"
        start = time.perf_counter()
        try:
            # Check root or docs endpoint
            status, _, duration = self._http_request("/")
            passed = status in (200, 404)  # 404 is acceptable if root has no GET, but server responds
            return TestResult(
                name=name,
                description=desc,
                passed=passed,
                duration_ms=duration,
                response_summary=f"HTTP status: {status}",
            )
        except Exception as exc:
            return TestResult(
                name=name,
                description=desc,
                passed=False,
                duration_ms=(time.perf_counter() - start) * 1000,
                error_message=str(exc),
            )

    # ---- identity check: make sure the server on this port IS the project under test -------------
    TEMPLATE_SAMPLE_TOOLS = ("get_current_time", "send_message")

    @staticmethod
    def _expected_tools(project: Path) -> tuple[set[str], set[str]]:
        """(local @tool names, agent.toml tool ids) declared by the project."""
        local: set[str] = set()
        for f in (project / "agent" / "tools").glob("*.py"):
            for m in re.finditer(r"@tool[^\n]*\n\s*(?:async\s+)?def\s+(\w+)", f.read_text(encoding="utf-8")):
                local.add(m.group(1))
        toml_ids: set[str] = set()
        toml = project / "agent.toml"
        if toml.exists():
            toml_ids = set(re.findall(r'^id\s*=\s*"([^"]+)"', toml.read_text(encoding="utf-8"), re.M))
        return local, toml_ids

    @staticmethod
    def _port_owner(port: int) -> Optional[dict[str, str]]:
        """Owner of ``port`` (see check_environment.port_owner); None if the port is free."""
        from check_environment import port_owner  # same scripts directory

        return port_owner(port)

    def test_identity(self, project_dir: str) -> TestResult:
        """Test 0: the server must be the agent in ``project_dir`` (not a stale/other agent)."""
        name = "0. Agent Identity (right project on this port)"
        desc = "Port owner cwd and the agent's reported tools must match the project"
        project = Path(project_dir).resolve()
        start = time.perf_counter()
        problems: list[str] = []
        notes: list[str] = []

        port = urlparse(self.base_url).port or 80
        owner = self._port_owner(port)
        if owner is not None:
            proj = str(project).lower()
            where = owner["cwd"] or owner["exe"] or owner["cmd"]
            if owner["cwd"]:  # Linux/macOS: the working directory identifies the project
                if not Path(owner["cwd"]).resolve().is_relative_to(project):
                    problems.append(f"port {port} is served by pid {owner['pid']} running in {owner['cwd']}, not {project}")
            elif owner["exe"] or owner["cmd"]:  # Windows: the project's .venv python / command line
                if proj not in (owner["exe"] + " " + owner["cmd"]).lower():
                    notes.append(f"pid {owner['pid']} ({where[:80]}) has no path under the project; relying on the tool probe")

        local, toml_ids = self._expected_tools(project)
        try:
            endpoint = self._detect_endpoint()
            payload = self._build_payload(
                endpoint,
                [{"role": "user", "content": "List the exact names of every tool you can call, "
                  "comma-separated, no other text."}],
            )
            status, res, _ = self._http_request(endpoint, method="POST", data=payload)
            _, text = self._extract_content_full(res)
            text_l = text.lower()
            if status != 200:
                problems.append(f"tool listing request failed: HTTP {status}")
            else:
                for t in sorted(local):
                    if t.lower() not in text_l:
                        problems.append(f"expected local tool '{t}' not reported by the agent")
                for t in self.TEMPLATE_SAMPLE_TOOLS:
                    if t not in local and t in text_l:
                        problems.append(f"agent reports template sample tool '{t}' that this project no longer has "
                                        "(stale server?)")
                for t in sorted(toml_ids):
                    if t.lower() not in text_l:
                        notes.append(f"agent.toml tool '{t}' not named in the reply (MCP tool names may differ)")
        except Exception as exc:
            problems.append(f"identity probe failed: {exc}")

        return TestResult(
            name=name,
            description=desc,
            passed=not problems,
            duration_ms=(time.perf_counter() - start) * 1000,
            error_message="; ".join(problems) or None,
            response_summary=f"project={project.name}, local tools={sorted(local)}" + (f" | {'; '.join(notes)}" if notes else ""),
        )

    def _extract_content_full(self, res: Any) -> tuple[bool, str]:
        """Like _extract_content but without truncation."""
        ok, text = self._extract_content(res)
        if isinstance(res, dict):
            text = json.dumps(res, ensure_ascii=False)
        return ok, text

    def _detect_endpoint(self) -> str:
        """Detect whether the server uses /api/invocations (DurableAgentServer) or /invocations."""
        for ep in ("/api/invocations", "/invocations"):
            try:
                # Send minimal options or post check
                status, _, _ = self._http_request(ep, method="POST", data={})
                # If we get 400 or 422, the endpoint exists and validates payloads
                if status in (400, 422, 200, 405):
                    return ep
            except Exception:
                pass
        return "/api/invocations"

    def _extract_content(self, res: Any) -> tuple[bool, str]:
        """Extract text content from various agent response formats."""
        if not isinstance(res, dict):
            return bool(res), str(res)[:120]

        # Case 1: Agent Bricks DurableAgentServer output dict
        output_obj = res.get("output")
        if isinstance(output_obj, dict):
            inner_output = output_obj.get("output")
            if isinstance(inner_output, list) and inner_output:
                last_item = inner_output[-1]
                if isinstance(last_item, dict) and "content" in last_item:
                    return bool(last_item["content"]), str(last_item["content"])[:120]
            if "content" in output_obj:
                return bool(output_obj["content"]), str(output_obj["content"])[:120]

        # Case 2: Standard messages array
        if "messages" in res and isinstance(res["messages"], list):
            last_msg = res["messages"][-1] if res["messages"] else {}
            content = last_msg.get("content", "")
            return bool(content), str(content)[:120]

        # Case 3: Flat output/response/result fields
        for key in ("output", "response", "result"):
            if key in res and res[key]:
                return True, str(res[key])[:120]

        return False, ""

    def _build_payload(self, endpoint: str, messages: list[dict[str, Any]], session_id: Optional[str] = None) -> dict[str, Any]:
        """Build request payload conforming to the detected server schema."""
        sess_id = session_id or f"test-sess-{uuid.uuid4().hex[:8]}"
        if endpoint.startswith("/api/"):
            return {
                "id": str(uuid.uuid4()),
                "input": {
                    "session_id": sess_id,
                    "messages": messages,
                },
            }
        else:
            payload: dict[str, Any] = {"messages": messages}
            if session_id:
                payload["session_id"] = session_id
            return payload

    def test_basic_conversation(self) -> TestResult:
        """Test 2: Basic query invocation."""
        name = "2. Basic Conversational Capability"
        desc = "Send a simple message and verify valid response structure"
        messages = [
            {"role": "user", "content": "Hello! Please reply with a short confirmation message."}
        ]
        endpoint = self._detect_endpoint()
        payload = self._build_payload(endpoint, messages)
        try:
            status, res, duration = self._http_request(endpoint, method="POST", data=payload)
            if status != 200:
                return TestResult(
                    name=name,
                    description=desc,
                    passed=False,
                    duration_ms=duration,
                    error_message=f"Expected HTTP 200, got {status}: {res}",
                )

            has_content, summary = self._extract_content(res)
            if not has_content:
                return TestResult(
                    name=name,
                    description=desc,
                    passed=False,
                    duration_ms=duration,
                    error_message="Response payload lacked expected message or output content.",
                    details={"raw_response": str(res)[:300]},
                )

            return TestResult(
                name=name,
                description=desc,
                passed=True,
                duration_ms=duration,
                response_summary=f"Output: '{summary}'",
                details={"status": status},
            )
        except Exception as exc:
            return TestResult(
                name=name,
                description=desc,
                passed=False,
                duration_ms=0.0,
                error_message=f"Request failed: {exc}",
            )

    def test_session_continuity(self) -> TestResult:
        """Test 3: Verify multi-turn memory within a session."""
        name = "3. Session & Context Continuity"
        desc = "Verify context persists across multiple turns with the same session_id"
        session_id = f"test-sess-{uuid.uuid4().hex[:8]}"
        endpoint = self._detect_endpoint()

        try:
            # Turn 1: Provide a distinct fact
            secret_word = f"Pineapple{uuid.uuid4().hex[:4]}"
            payload_turn1 = self._build_payload(
                endpoint,
                [{"role": "user", "content": f"My secret code is '{secret_word}'. Remember it."}],
                session_id=session_id,
            )
            status1, res1, dur1 = self._http_request(endpoint, method="POST", data=payload_turn1)
            if status1 != 200:
                return TestResult(
                    name=name,
                    description=desc,
                    passed=False,
                    duration_ms=dur1,
                    error_message=f"Turn 1 failed with HTTP {status1}: {res1}",
                )

            # Turn 2: Ask for the fact back
            payload_turn2 = self._build_payload(
                endpoint,
                [{"role": "user", "content": "What was my secret code? Reply with just the code."}],
                session_id=session_id,
            )
            status2, res2, dur2 = self._http_request(endpoint, method="POST", data=payload_turn2)
            total_dur = dur1 + dur2
            if status2 != 200:
                return TestResult(
                    name=name,
                    description=desc,
                    passed=False,
                    duration_ms=total_dur,
                    error_message=f"Turn 2 failed with HTTP {status2}: {res2}",
                )

            res2_text = json.dumps(res2)
            if secret_word.lower() in res2_text.lower():
                return TestResult(
                    name=name,
                    description=desc,
                    passed=True,
                    duration_ms=total_dur,
                    response_summary=f"Successfully recalled session context: '{secret_word}'",
                )
            else:
                return TestResult(
                    name=name,
                    description=desc,
                    passed=False,
                    duration_ms=total_dur,
                    error_message=f"Context not recalled. Expected '{secret_word}' in response.",
                    details={"turn2_response": str(res2)[:300]},
                )
        except Exception as exc:
            return TestResult(
                name=name,
                description=desc,
                passed=False,
                duration_ms=0.0,
                error_message=f"Session test exception: {exc}",
            )

    def test_error_handling(self) -> TestResult:
        """Test 4: Graceful handling of invalid requests."""
        name = "4. Error & Boundary Handling"
        desc = "Verify server rejects invalid body gracefully without crashing (500)"
        endpoint = self._detect_endpoint()
        try:
            # Send invalid structure
            status, res, dur = self._http_request(endpoint, method="POST", data={"invalid_key": 123})
            # Should be 4xx client error (e.g. 400 or 422 Unprocessable Entity), not 500
            passed = status in (400, 422) or status == 200
            if passed:
                return TestResult(
                    name=name,
                    description=desc,
                    passed=True,
                    duration_ms=dur,
                    response_summary=f"Handled invalid payload with status HTTP {status}",
                )
            else:
                return TestResult(
                    name=name,
                    description=desc,
                    passed=False,
                    duration_ms=dur,
                    error_message=f"Unexpected status for malformed input: HTTP {status} (Expected 400/422)",
                    details={"response": res},
                )
        except Exception as exc:
            return TestResult(
                name=name,
                description=desc,
                passed=False,
                duration_ms=0.0,
                error_message=f"Error handling test exception: {exc}",
            )

    def run_all(
        self, custom_queries: Optional[list[str]] = None, project_dir: Optional[str] = None
    ) -> list[TestResult]:
        results: list[TestResult] = []

        # 1. Health
        results.append(self.test_health_check())
        if not results[-1].passed:
            # If server is not reachable, skip remaining tests
            return results

        # 1b. Identity: is this really the project under test? (stops stale-server false passes)
        if project_dir:
            results.append(self.test_identity(project_dir))
            if not results[-1].passed:
                return results

        # 2. Basic conversation
        results.append(self.test_basic_conversation())

        # 3. Session continuity
        results.append(self.test_session_continuity())

        # 4. Error handling
        results.append(self.test_error_handling())

        # 5. Optional custom queries (e.g. tool execution tests)
        if custom_queries:
            endpoint = self._detect_endpoint()
            for idx, query in enumerate(custom_queries, 1):
                name = f"5.{idx}. Custom Query Test: '{query[:40]}...'"
                desc = f"Execute custom user-defined query: {query}"
                payload = self._build_payload(endpoint, [{"role": "user", "content": query}])
                try:
                    status, res, dur = self._http_request(endpoint, method="POST", data=payload)
                    passed = status == 200
                    _, summary = self._extract_content(res)
                    results.append(
                        TestResult(
                            name=name,
                            description=desc,
                            passed=passed,
                            duration_ms=dur,
                            error_message=None if passed else f"HTTP {status}: {res}",
                            response_summary=summary or str(res)[:120],
                        )
                    )
                except Exception as exc:
                    results.append(
                        TestResult(
                            name=name,
                            description=desc,
                            passed=False,
                            duration_ms=0.0,
                            error_message=str(exc),
                        )
                    )

        return results



def main() -> int:
    parser = argparse.ArgumentParser(description="Test local Agent Bricks API endpoint.")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL of local agent server")
    parser.add_argument("--timeout", type=float, default=45.0, help="Per-request timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--project", help="Project dir under test; enables the identity check (recommended)")
    parser.add_argument("--custom-query", action="append", help="Add custom query to test (can repeat)")

    args = parser.parse_args()

    tester = LocalAgentApiTester(base_url=args.url, timeout=args.timeout)
    results = tester.run_all(custom_queries=args.custom_query, project_dir=args.project)

    all_passed = all(r.passed for r in results)

    if args.json:
        payload = {
            "all_passed": all_passed,
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [asdict(r) for r in results],
        }
        print(json.dumps(payload, indent=2))
    else:
        print("\n" + "=" * 70)
        print("  Databricks Agent Bricks - Local API Test Suite")
        print(f"  Target: {args.url}")
        print("=" * 70)
        for r in results:
            status_icon = "[PASS]" if r.passed else "[FAIL]"
            color_mark = "\033[92m[PASS]\033[0m" if r.passed else "\033[91m[FAIL]\033[0m"
            print(f"\n{color_mark} {r.name} ({r.duration_ms:.1f}ms)")
            print(f"       Description: {r.description}")
            if r.response_summary:
                print(f"       Summary:     {r.response_summary}")
            if r.error_message:
                print(f"       Error:       {r.error_message}")

        print("\n" + "-" * 70)
        passed_count = sum(1 for r in results if r.passed)
        print(f"Test Summary: {passed_count}/{len(results)} passed.")
        if all_passed:
            print("Verdict: ALL LOCAL API TESTS PASSED! Ready for deployment.\n")
        else:
            print("Verdict: SOME TESTS FAILED. Triggering self-correction loop.\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

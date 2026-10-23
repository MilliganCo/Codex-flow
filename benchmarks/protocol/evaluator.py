#!/usr/bin/env python3
"""Frozen neutral ASCII Tree evaluator. Stdlib only; no installs or model calls.

Discover only documented Python CLI contracts or project.scripts metadata. No
implementation-specific imports, fixtures or API assumptions. Discovery failure
is NOT_ASSESSED. Execute only after solutions finish. Never expose this directory
or output to benchmark executors. Frame checks do not prove geometry or aesthetics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import signal
import subprocess
import sys
import time
import tomllib

HERE = Path(__file__).resolve().parent
ANSI = re.compile(rb"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
FLAGS = {
    "seed": ("--seed",), "width": ("--width", "-W"),
    "height": ("--height", "-H"), "mode": ("--mode", "--dimension", "--dim"),
    "output": ("--output", "--out", "-o"),
    "angle3": ("--yaw", "--azimuth", "--angle", "--rotate-y", "--rotation-y", "--camera-yaw"),
    "angle4": ("--angle4d", "--angle-4d", "--angle4", "--xw", "--xw-angle", "--hyper-angle", "--hyper", "--rotation-4d", "--w-angle"),
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], cwd: Path, env: dict, timeout: float) -> dict:
    started = time.monotonic()
    kwargs = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    try:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    except OSError as exc:
        return {"command": command, "status": "not-assessed", "reason": str(exc), "duration_s": time.monotonic() - started}
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=10)
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        stdout, stderr = proc.communicate(timeout=10)
    return {"command": command, "status": "fail" if timed_out or proc.returncode else "pass",
            "returncode": proc.returncode, "timeout": timed_out,
            "duration_s": round(time.monotonic() - started, 6),
            "stdout": stdout.decode("utf-8", "replace")[-60000:],
            "stderr": stderr.decode("utf-8", "replace")[-12000:],
            "stdout_bytes": len(stdout), "stdout_sha256": hashlib.sha256(stdout).hexdigest()}


def read_docs(root: Path) -> str:
    docs = []
    for path in sorted(root.glob("README*")):
        if path.is_file() and path.stat().st_size <= 1024 * 1024:
            docs.append(path.read_text(encoding="utf-8-sig", errors="replace"))
    return "\n".join(docs)


def discover(root: Path, docs: str, python: str) -> list[dict]:
    candidates = []
    seen = set()
    for match in re.finditer(r"(?:python(?:3(?:\.\d+)?)?(?:\.exe)?|py\s+-3)\s+(?:-m\s+([\w.]+)|([\w./\\-]+\.py))", docs):
        module, script = match.groups()
        if module in {"unittest", "pytest", "pip", "venv", "compileall", "http.server"}:
            continue
        if module:
            parts = Path(*module.split("."))
            found = any((base / parts.with_suffix(".py")).is_file() or (base / parts / "__main__.py").is_file()
                        for base in (root, root / "src"))
            prefix = [python, "-m", module]
        else:
            script = script.replace("\\", "/")
            target = (root / script).resolve()
            found = target.is_relative_to(root) and target.is_file()
            prefix = [python, script]
        if found and tuple(prefix) not in seen:
            candidates.append({"prefix": prefix, "source": "README command"})
            seen.add(tuple(prefix))
    project = root / "pyproject.toml"
    if project.is_file():
        try:
            data = tomllib.loads(project.read_text(encoding="utf-8-sig"))
        except (ValueError, OSError):
            data = {}
        for name, entry in data.get("project", {}).get("scripts", {}).items():
            if not isinstance(entry, str) or not re.fullmatch(r"[\w.]+:[\w.]+", entry):
                continue
            module, function = entry.split(":")
            code = f"import sys; from {module} import {function} as entry; sys.argv[0]={name!r}; sys.exit(entry())"
            prefix = [python, "-c", code]
            if tuple(prefix) not in seen:
                candidates.append({"prefix": prefix, "source": "pyproject project.scripts", "entrypoint": name})
                seen.add(tuple(prefix))
    return candidates


def flag(help_text: str, names: tuple[str, ...]) -> str | None:
    for name in names:
        if re.search(r"(?<![\w-])" + re.escape(name) + r"(?=[\s,=\[\]}]|$)", help_text):
            return name
    return None


def discover_contract(candidates: list[dict], root: Path, docs: str, env: dict, timeout: float) -> tuple[dict | None, list]:
    probes = []
    for candidate in candidates[:8]:
        prefix = candidate["prefix"]
        help_result = run(prefix + ["--help"], root, env, timeout)
        probes.append(help_result)
        help_text = help_result.get("stdout", "") + help_result.get("stderr", "")
        if help_result["status"] != "pass" or not help_text.strip():
            continue
        render_tokens = []
        if re.search(r"\brender\b", help_text):
            render_tokens = ["render"]
        elif re.search(r"(?<![\w-])--headless\b", help_text):
            render_tokens = ["--headless"]
        elif re.search(r"(?<![\w-])--render\b", help_text):
            render_tokens = ["--render"]
        else:
            continue
        render_help = run(prefix + render_tokens + ["--help"], root, env, timeout)
        probes.append(render_help)
        combined = help_text + "\n" + render_help.get("stdout", "") + render_help.get("stderr", "")
        options = {key: flag(combined, names) for key, names in FLAGS.items()}
        if all(options[key] for key in ("seed", "width", "height", "mode")):
            mode_values = {mode: mode for mode in ("2d", "3d", "4d")}
            if re.search(r"\b2D\b", combined) and not re.search(r"\b2d\b", combined):
                mode_values = {mode: mode.upper() for mode in mode_values}
            return {**candidate, "render_tokens": render_tokens, "flags": options,
                    "mode_values": mode_values, "help": help_result, "render_help": render_help}, probes
    return None, probes


def frame_check(raw: bytes, width: int, height: int) -> dict:
    # Accept a single conventional final newline and either LF or CRLF; every row
    # must still be exactly width characters, with exactly height rows.
    lines = raw.splitlines()
    printable = all(32 <= byte <= 126 or byte in (10, 13) for byte in raw)
    sizes = len(lines) == height and all(len(line) == width for line in lines)
    no_ansi = not ANSI.search(raw) and b"\x1b" not in raw
    return {"printable_ascii": printable, "no_ansi": no_ansi, "size_ok": sizes,
            "line_count": len(lines), "line_widths": sorted(set(map(len, lines))),
            "nonspace_characters": sum(byte not in b" \r\n" for byte in raw),
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
            "status": "pass" if printable and no_ansi and sizes else "fail"}


def render(contract: dict, root: Path, env: dict, timeout: float, output: Path,
           mode: str, seed: int, width: int, height: int, angle: tuple[str, float] | None = None) -> dict:
    command = contract["prefix"] + contract["render_tokens"]
    values = {"mode": contract["mode_values"][mode], "seed": str(seed), "width": str(width), "height": str(height)}
    for name, value in values.items():
        command += [contract["flags"][name], value]
    if contract["flags"]["output"]:
        command += [contract["flags"]["output"], str(output)]
    if angle:
        command += [angle[0], str(angle[1])]
    result = run(command, root, env, timeout)
    result.update({"mode": mode, "seed": seed, "width": width, "height": height, "output": str(output)})
    if result["status"] != "pass":
        return result
    if contract["flags"]["output"]:
        if not output.is_file():
            result.update(status="fail", reason="Output flag accepted but output file absent")
            return result
        raw = output.read_bytes()
    else:
        # Only stdout-based render contracts use stdout as raster evidence.
        raw = result.get("stdout", "").encode("utf-8")
        output.write_bytes(raw)
    result["frame"] = frame_check(raw, width, height)
    return result


def test_command(root: Path, docs: str, python: str, env: dict, timeout: float) -> dict:
    for line in docs.splitlines():
        matched = re.search(r"\b(?:python(?:3(?:\.\d+)?)?|py\s+-3)\s+-m\s+(unittest|pytest)\b(.*)", line)
        if not matched:
            continue
        tail = matched.group(2).strip().strip("`")
        if any(ch in tail for ch in "|;&><$"):
            continue
        try:
            tokens = shlex.split(tail)
        except ValueError:
            continue
        return run([python, "-m", matched.group(1)] + tokens, root, env, timeout)
    tests = root / "tests"
    if tests.is_dir() and any(tests.rglob("test_*.py")):
        imports_pytest = any(re.search(r"(?:^|\n)\s*(?:import pytest|from pytest)", p.read_text(encoding="utf-8", errors="replace"))
                             for p in tests.rglob("test_*.py") if p.stat().st_size < 1024 * 1024)
        command = [python, "-m", "pytest", "-q"] if imports_pytest else [python, "-m", "unittest", "discover", "-s", "tests", "-v"]
        return run(command, root, env, timeout)
    return {"status": "not-assessed", "reason": "No safely discoverable documented Python test command or tests/test_*.py"}


def evaluate(root: Path, output: Path, python: str, timeout: float) -> dict:
    rubric = json.loads((HERE / "rubric.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=False)
    docs = read_docs(root)
    env = dict(os.environ)
    # No credential inspection: inherit normal environment except deterministic
    # Python/test controls. The evaluator never logs environment values.
    env.update(PYTHONPATH=str(root / "src") + os.pathsep + str(root), PYTHONHASHSEED="0",
               PYTHONDONTWRITEBYTECODE="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", NO_COLOR="1", TERM="dumb")
    candidates = discover(root, docs, python)
    contract, probes = discover_contract(candidates, root, docs, env, timeout)
    report = {"schema": 1, "solution": str(root), "rubric_sha256": sha(HERE / "rubric.json"),
              "evaluator_sha256": sha(Path(__file__)), "cli": contract, "discovery_probes": probes,
              "frames": [], "tests": None, "categories": [], "quality_score": None,
              "accepted": None, "acceptance_reason": "Blind review and interactive checks remain required",
              "discovery_status": "pass" if contract else "not-assessed",
              "discovery_reason": None if contract else "No supported documented Python headless CLI discovered; no quality failure inferred"}
    observations = {}

    def observed(key: str, success: bool, evidence: list, reason: str = "") -> None:
        observations[key] = {"status": "pass" if success else "fail", "evidence": evidence, "reason": reason}

    if contract:
        observed("ux.help", True, ["cli.help"])
        for mode in ("2d", "3d", "4d"):
            for seed in (42, 137):
                dimensions = (80, 30) if seed == 42 else (100, 40)
                record = render(contract, root, env, timeout, output / f"{mode}-{seed}.txt", mode, seed, *dimensions)
                report["frames"].append(record)
        standard = list(report["frames"])
        observed("reliability.headless", all(r["status"] == "pass" for r in standard), ["frames[0:6]"])
        observed("ux.export", all(r.get("frame", {}).get("status") == "pass" for r in standard), ["frames[0:6].frame"])
        repeats = [render(contract, root, env, timeout, output / f"{r['mode']}-{r['seed']}-repeat.txt",
                          r["mode"], r["seed"], r["width"], r["height"]) for r in standard]
        report["frames"].extend(repeats)
        report["repeat_determinism"] = [{"mode": original["mode"], "seed": original["seed"],
            "status": "pass" if original.get("frame", {}).get("sha256") is not None and
            original.get("frame", {}).get("sha256") == repeated.get("frame", {}).get("sha256") else "fail"}
            for original, repeated in zip(standard, repeats)]
        repeated = repeats[0]
        first = standard[0].get("frame", {}).get("sha256")
        observed("2d.determinism", first is not None and first == repeated.get("frame", {}).get("sha256"), ["2d-42.txt", "2d-42-repeat.txt"])
        # Compare seeds at the SAME size, so dimension changes cannot masquerade as seed variation.
        second_seed = render(contract, root, env, timeout, output / "2d-137-same-size.txt", "2d", 137, 80, 30)
        report["frames"].append(second_seed)
        observed("2d.seed_variation", first is not None and second_seed.get("frame", {}).get("sha256") is not None and first != second_seed["frame"]["sha256"], ["2d-42.txt", "2d-137-same-size.txt"])
        tiny = []
        for mode in ("2d", "3d", "4d"):
            tiny.append(render(contract, root, env, timeout, output / f"{mode}-tiny.txt", mode, 42, 2, 2))
        report["frames"].extend(tiny)
        observed("reliability.tiny", all(r["status"] == "pass" and r.get("frame", {}).get("status") == "pass" for r in tiny), ["*-tiny.txt"])
        for mode, angle_key in (("3d", "angle3"), ("4d", "angle4")):
            angle_flag = contract["flags"][angle_key]
            if angle_flag is None:
                continue
            # Respect documented units if the option's help line states degrees.
            # Default radians is a discovery limitation, not a mathematics verdict.
            help_text = contract["render_help"].get("stdout", "") + contract["render_help"].get("stderr", "")
            option_lines = [line for line in help_text.splitlines() if angle_flag in line]
            angle_value = 37 if re.search(r"\b(?:degrees?|deg)\b", " ".join(option_lines), re.I) else 0.65
            records = [render(contract, root, env, timeout, output / f"{mode}-angle-{value}.txt", mode, 42, 100, 40, (angle_flag, value)) for value in (0, angle_value)]
            report["frames"].extend(records)
            hashes = [r.get("frame", {}).get("sha256") for r in records]
            observed(f"{mode}.angular_change", all(r["status"] == "pass" and r.get("frame", {}).get("status") == "pass" for r in records) and None not in hashes and hashes[0] != hashes[1], [r["output"] for r in records], "Changed bytes are necessary evidence; source review must separately establish true transformations")
    report["tests"] = test_command(root, docs, python, env, max(timeout, 90))
    test_result = report["tests"]
    test_text = test_result.get("stdout", "") + test_result.get("stderr", "")
    counts = re.findall(r"Ran\s+(\d+)\s+tests?", test_text)
    if counts:
        count = int(counts[-1])
    else:
        counts = re.findall(r"\b(\d+)\s+passed\b", test_text)
        count = int(counts[-1]) if counts else None
    test_result["observed_test_count"] = count
    if test_result["status"] != "not-assessed":
        observed("tests.execution", test_result["status"] == "pass" and count is not None and count > 0, ["tests"], "Zero tests or unknown test counts cannot establish a passing test suite")
    assessed_points = assessed_max = 0
    for category in rubric["categories"]:
        category_result = {"id": category["id"], "max": category["max"], "score": None, "status": "not-assessed", "evidence": [], "reason": "Some criteria require separate blind review", "criteria": []}
        for criterion in category["criteria"]:
            obs = observations.get(criterion["id"], {"status": "not-assessed", "evidence": [], "reason": criterion["method"]})
            score = criterion["max"] if obs["status"] == "pass" else 0 if obs["status"] == "fail" else None
            category_result["criteria"].append({"id": criterion["id"], "max": criterion["max"], "score": score, **obs})
            if score is not None:
                assessed_points += score
                assessed_max += criterion["max"]
        if all(item["score"] is not None for item in category_result["criteria"]):
            category_result["score"] = sum(item["score"] for item in category_result["criteria"])
            category_result["status"] = "pass" if category_result["score"] == category_result["max"] else "partial" if category_result["score"] else "fail"
            category_result["reason"] = "All criteria assessed"
        report["categories"].append(category_result)
    report["assessed_points"] = assessed_points
    report["assessed_max"] = assessed_max
    report["unassessed_max"] = rubric["total_max"] - assessed_max
    (output / "evaluation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("solution", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="new external results directory")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    root = args.solution.resolve()
    output = args.output.resolve()
    if not root.is_dir() or output.is_relative_to(root) or args.timeout <= 0:
        parser.error("solution must exist, output must be outside solution, timeout must be positive")
    report = evaluate(root, output, args.python, args.timeout)
    print(json.dumps({"discovery_status": report["discovery_status"], "assessed_points": report["assessed_points"], "assessed_max": report["assessed_max"], "quality_score": None, "accepted": None, "result": str(output / "evaluation.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

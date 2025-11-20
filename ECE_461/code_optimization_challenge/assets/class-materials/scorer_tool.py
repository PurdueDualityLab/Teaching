import argparse
import subprocess
import sys
import os
import json
import time
import shutil
from pathlib import Path
from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument("--LLM-client", choices=["ollama", "openai"], required=True)
parser.add_argument(
    "--trials",
    type=int,
    default=11,
    help="Number of benchmark trials to run per problem (default: 11).",
)

# -------------------------------------------------------------------
# Config: paths
# -------------------------------------------------------------------
AGENT_RUN = Path(__file__).parent / "student_agent" / "my-agent.py"  # the student agent template
BENCH_ROOT = Path("local_benchmarks")  # root folder with problem folders
WORK_ROOT = Path("work")               # temp workspace for student runs
WORK_ROOT.mkdir(exist_ok=True)
args = parser.parse_args()

# Map logical LLM client choice to a concrete client file for my-agent.py
if args.LLM_client == "ollama":
    LLM_CLIENT_PATH = Path(__file__).parent / "student_agent" / "ollama-client.py"

elif args.LLM_client == "openai":
    LLM_CLIENT_PATH = Path(__file__).parent / "student_agent" / "openai-client.py"

else:
    raise ValueError(f"Unsupported LLM client: {args.LLM_client}")

# -------------------------------------------------------------------
# Utility to run a Python file with a test
# -------------------------------------------------------------------
def run_test(py_file, test):
    start = time.perf_counter()
    process = subprocess.Popen(
        [sys.executable, str(py_file)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = process.communicate(input=test["input"])
    elapsed = (time.perf_counter() - start) * 1000  # ms
    return stdout, stderr, process.returncode, elapsed

# -------------------------------------------------------------------
# Run a benchmark (starter or optimized code)
# -------------------------------------------------------------------
def run_single_benchmark(json_path, code_path, trials: int):
    """
    Run the benchmark multiple times to reduce noise.

    We run `trials` times, discard the first run (warm-up), and average the
    remaining runs. Correctness is required on every run.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    tests = cfg["tests"]
    py_file = code_path

    trial_times = []
    trial_passes = []

    for trial in range(trials):
        all_passed = True
        total_time = 0.0

        for t in tests:
            out, err, code, duration_ms = run_test(py_file, t)
            total_time += duration_ms
            expected = t["expected_output"]

            if out != expected or code != 0:
                all_passed = False

        trial_times.append(total_time)
        trial_passes.append(all_passed)

    # Discard the first run as a warm-up and average the rest.
    if trials > 1:
        effective_times = trial_times[1:]
    else:
        effective_times = trial_times

    avg_time = sum(effective_times) / len(effective_times)
    all_trials_passed = all(trial_passes)

    return all_trials_passed, avg_time

# -------------------------------------------------------------------
# Main evaluation loop per problem
# -------------------------------------------------------------------
def evaluate_problem(problem_dir, llm_client):
    problem_dir = Path(problem_dir)
    # Find benchmark JSON
    # Ignore macOS AppleDouble/metadata files like '._problem.json'
    json_files = sorted(
        [p for p in problem_dir.glob("*.json") if not p.name.startswith("._")]
    )
    if not json_files:
        print(f"No JSON found for {problem_dir}")
        return None

    # Prefer a file literally named '<problem>.json' if present; otherwise take first.
    json_file = None
    problem_base = problem_dir.name + ".json"
    for p in json_files:
        if p.name == problem_base:
            json_file = p
            break
    if json_file is None:
        json_file = json_files[0]

    # Find starter Python code
    # Ignore macOS AppleDouble/metadata files like '._starter.py'
    py_files = sorted(
        [p for p in problem_dir.glob("*.py") if not p.name.startswith("._")]
    )
    if not py_files:
        print(f"No starter Python code found for {problem_dir}")
        return None

    # Prefer a file literally named 'starter.py' if present; otherwise, use the first.
    starter_code = None
    for p in py_files:
        if p.name == "starter.py":
            starter_code = p
            break
    if starter_code is None:
        starter_code = py_files[0]

    # Create per-run workspace
    temp_dir = WORK_ROOT / problem_dir.name
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    starter_copy = temp_dir / "starter.py"
    optimized_copy = temp_dir / "optimized.py"

    # Copy starter code to workspace
    shutil.copy(starter_code, starter_copy)

    # Run agent
    print(f"[DEBUG] Running agent command: {sys.executable}", file=sys.stderr)
    print(f"[DEBUG] CWD for agent: {os.getcwd()}", file=sys.stderr)
    try:
        agent_result = subprocess.run(
            [
                sys.executable,
                str(AGENT_RUN),
                "--llm-client",
                str(LLM_CLIENT_PATH),
                "--optimizeTarget",
                str(starter_copy),
                "--optimizedResult",
                str(optimized_copy),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print("\n[AGENT ERROR] my-agent.py failed", file=sys.stderr)
        print(f"[AGENT ERROR] Command: {e.cmd}", file=sys.stderr)
        print(f"[AGENT ERROR] Return code: {e.returncode}", file=sys.stderr)
        if e.stdout:
            print("\n[AGENT STDOUT]\n" + e.stdout, file=sys.stderr)
        if e.stderr:
            print("\n[AGENT STDERR]\n" + e.stderr, file=sys.stderr)
        raise
    else:
        if agent_result.stdout:
            print("\n[AGENT STDOUT]\n" + agent_result.stdout, file=sys.stderr)
        if agent_result.stderr:
            print("\n[AGENT STDERR]\n" + agent_result.stderr, file=sys.stderr)

    # Run benchmarks on both
    starter_passed, starter_time = run_single_benchmark(
        json_file, starter_copy, args.trials
    )
    optimized_passed, optimized_time = run_single_benchmark(
        json_file, optimized_copy, args.trials
    )

    improvement = starter_time - optimized_time
    correctness_score = 1.0 if optimized_passed else 0.0
    total_score = (
        correctness_score + (improvement / 1000.0)
        if correctness_score > 0
        else 0.0
    )

    return {
        "problem": problem_dir.name,
        "starter_time_ms": starter_time,
        "optimized_time_ms": optimized_time,
        "improvement_ms": improvement,
        "starter_correct": starter_passed,
        "optimized_correct": optimized_passed,
        "score": total_score,
    }

# -------------------------------------------------------------------
# Run all problems
# -------------------------------------------------------------------
def main():
    results = []
    for problem_dir in sorted(BENCH_ROOT.iterdir()):
        if problem_dir.is_dir():
            res = evaluate_problem(problem_dir, args.LLM_client)
            if res:
                results.append(res)

    print("\n========= SUMMARY =========")
    for r in results:
        print(
            f"{r['problem']}: starter_time={r['starter_time_ms']:.2f}ms, "
            f"optimized_time={r['optimized_time_ms']:.2f}ms, "
            f"improvement={r['improvement_ms']:.2f}ms, "
            f"score={r['score']:.2f}, "
            f"correct={r['optimized_correct']}"
        )

    total_score = sum(r["score"] for r in results)
    print(f"\nTOTAL SCORE: {total_score}")

if __name__ == "__main__":
    main()
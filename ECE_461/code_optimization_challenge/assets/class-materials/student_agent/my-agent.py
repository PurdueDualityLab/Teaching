"""
Minimal student agent harness.

Usage:
    python3 my-agent.py --llm-client llm.py --optimizeTarget input.py --optimizedResult output.py

This script:
  - Dynamically loads a class `LLMClient` from the given --llm-client file.
  - Expects that class to expose a method: chat(self, prompt: str) -> str
  - Provides the paths to the optimizeTarget input file and optimizedResult output file.
  - Leaves all actual agent logic up to the student.
"""

import argparse
import importlib.util
import sys
from pathlib import Path
from typing import Protocol, runtime_checkable, Any, Union, List, Dict


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Informal protocol for the injected LLM client."""

    def chat(self, prompt: Union[str, List[Dict[str, Any]]]) -> str:  # pragma: no cover
        """
        Send input to the LLM and return the model's response as a string.

        The `prompt` argument can be either:
          - a plain string (single-turn prompt), or
          - a list of message dicts, e.g.:
              [{"role": "user", "content": "Hello"}]
        Implementations are expected to handle both cases.
        """
        ...


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Student agent: optimize a target program using an injected LLM client."
    )
    default_llm = str(Path(__file__).parent / "ollama-client.py")
    parser.add_argument(
        "--llm-client",
        default=default_llm,
        help=(
            "Path to a Python file that defines class `LLMClient` with "
            "chat(prompt: str) -> str. Defaults to ollama-client.py in this directory."
        ),
    )
    parser.add_argument(
        "--optimizeTarget",
        required=True,
        help="Input file to optimize.",
    )
    parser.add_argument(
        "--optimizedResult",
        required=True,
        help="Output file to write the optimized result.",
    )
    return parser.parse_args()


def load_llm_client(module_path: str) -> LLMClientProtocol:
    """
    Dynamically import LLMClient from the given Python file.

    The file must define a class named `LLMClient` with a method:
        chat(self, prompt: str) -> str
    that returns the model's response as a string.
    """
    path = Path(module_path)
    if not path.exists():
        raise FileNotFoundError(f"--llm-client file not found: {path}")

    spec = importlib.util.spec_from_file_location("student_llm_client", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module from {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[arg-type]

    if not hasattr(module, "LLMClient"):
        raise AttributeError(
            f"{path} does not define a class named 'LLMClient'. "
            "Please implement class LLMClient with a .chat(prompt: str) -> str method."
        )

    cls = getattr(module, "LLMClient")
    client = cls()

    if not isinstance(client, LLMClientProtocol):
        # Best-effort runtime check; mainly to give a helpful error.
        if not hasattr(client, "chat") or not callable(getattr(client, "chat")):
            raise TypeError(
                "LLMClient instance does not implement the expected interface. "
                "It must provide chat(self, prompt) -> str where prompt is either "
                "a string or a list of {role, content} message dicts."
            )

    return client  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    args = parse_args()
    llm_client = load_llm_client(args.llm_client)
    target_path = Path(args.optimizeTarget)
    result_path = Path(args.optimizedResult)

    print(f"[INFO] Loaded LLM client from: {args.llm_client}")
    print(f"[INFO] Optimize target file: {target_path}")
    print(f"[INFO] Optimized result file: {result_path}")

    if not target_path.exists():
        print(f"[WARN] Target file does not exist yet: {target_path}")


    # ------------------------------------------------------------------
    # Example scaffold: Maintain message history and perform 3 iterations.
    # Students may completely replace this block with their own logic.
    # ------------------------------------------------------------------
    messages: List[Dict[str, Any]] = []
    iteration = 0

    # Initial system instruction (students may change/remove this)
    messages.append({
        "role": "system",
        "content": (
            "You are a code optimization assistant. "
            "You will suggest improvements to the target program. "
            "Keep responses concise."
        )
    })

    # Initial user message (students may change/remove this)
    messages.append({
        "role": "user",
        "content": (
            f"The file to optimize is '{target_path.name}'. "
            "What is the first change you suggest?"
        )
    })

    while True:
        iteration += 1
        print(f"[INFO] Iteration {iteration}: sending {len(messages)} messages to LLM")

        try:
            response_text = llm_client.chat(messages)
        except Exception as e:
            print(f"[ERROR] LLM client raised an exception: {type(e).__name__}: {e}")
            return 1

        print("\n[LLM RESPONSE]")
        print(response_text)

        # Append model's message to history
        messages.append({
            "role": "assistant",
            "content": response_text,
        })

        # Example exit condition: stop after 3 iterations
        if iteration >= 1:
            print("[INFO] Stopping after 3 iterations (scaffold condition).\n")
            break

        # Add a follow-up user turn (students may replace this entirely)
        messages.append({
            "role": "user",
            "content": "Please continue refining your optimization suggestions."
        })

    # Default behavior: simply copy optimizeTarget to optimizedResult.
    try:
        result_path.write_text(target_path.read_text())
        print(f"[INFO] Wrote optimized result to {result_path} (default = copy).")
    except Exception as e:
        print(f"[ERROR] Failed to write optimized result: {e}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

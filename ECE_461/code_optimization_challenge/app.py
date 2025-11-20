#!/usr/bin/env python3

import os
import sqlite3
import time
import logging
import argparse
import tempfile
import zipfile
import shutil
import subprocess
import sys
import json
from flask import Flask, request, redirect, url_for, send_from_directory

# Configuration
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "leaderboard.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "submissions")
LOG_DIR = os.path.join(BASE_DIR, "logs")
ALLOWED_EXTENSIONS = {"zip"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# Global frontend logger placeholder; configured in __main__
FRONTEND_LOGGER = logging.getLogger("frontend")

# Global LLM client choice; set from CLI args in __main__
LLM_CLIENT_CHOICE = "ollama"

# --- Custom logging handler that flushes after every record ---
class FlushingFileHandler(logging.FileHandler):
    """FileHandler that flushes on every emit for real-time log visibility."""

    def emit(self, record):
        super().emit(record)
        try:
            self.flush()
        except Exception:
            # Avoid breaking logging on flush errors
            pass


def setup_frontend_logging():
    """Configure logging for the frontend (Flask) process."""
    logger = logging.getLogger("frontend")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        fh = FlushingFileHandler(os.path.join(LOG_DIR, "frontend.log"))
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger


def setup_runner_logging(runner_id: int):
    """Configure logging for a runner process with a given ID."""
    logger_name = f"runner-{runner_id}"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        fh = FlushingFileHandler(
            os.path.join(LOG_DIR, f"runner-{runner_id}.log")
        )
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    return logger

class Database:
    """Thin wrapper around sqlite3 for leaderboard operations."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        """Initialize the leaderboard DB if it does not exist."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pending_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                zip_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'REGISTERING',
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS completed_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                latency_reduction REAL,
                score REAL,
                per_problem_scores TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # For existing DBs created before per_problem_scores was added, ensure the column exists.
        try:
            cur.execute(
                "ALTER TABLE completed_runs ADD COLUMN per_problem_scores TEXT;"
            )
        except sqlite3.OperationalError:
            # Column already exists; ignore.
            pass
        conn.commit()
        conn.close()

    def insert_pending_job(self, name: str, zip_path: str) -> int:
        """Insert a new pending job and return its job id."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pending_jobs (name, zip_path, status)
            VALUES (?, ?, 'REGISTERING')
            """,
            (name, zip_path),
        )
        conn.commit()
        job_id = cur.lastrowid
        conn.close()
        return job_id

    def fetch_next_pending_job(self):
        """Atomically fetch the next pending job and mark it RUNNING.

        Returns a dict with keys: id, name, zip_path; or None if no pending jobs.
        """
        conn = self._connect()
        # Manage transactions manually so we can use BEGIN IMMEDIATE.
        conn.isolation_level = None
        cur = conn.cursor()

        # Acquire a RESERVED lock so no other writer can see/update the same row.
        cur.execute("BEGIN IMMEDIATE")

        cur.execute(
            """
            SELECT id, name, zip_path
            FROM pending_jobs
            WHERE status = 'PENDING'
            ORDER BY id ASC
            LIMIT 1;
            """
        )
        row = cur.fetchone()
        if row is None:
            cur.execute("COMMIT")
            conn.close()
            return None

        cur.execute(
            "UPDATE pending_jobs SET status = 'RUNNING' WHERE id = ?;",
            (row["id"],),
        )

        cur.execute("COMMIT")
        conn.close()
        return {"id": row["id"], "name": row["name"], "zip_path": row["zip_path"]}

    def complete_job_with_error(
        self, job_id: int, name: str, error_message: str = "Not implemented yet"
    ):
        """Record a completed job with status 'error' and remove it from pending."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO completed_runs (
                job_id, name, latency_reduction, score, per_problem_scores, status, error_message
            )
            VALUES (?, ?, NULL, NULL, NULL, 'error', ?);
            """,
            (job_id, name, error_message),
        )
        cur.execute("DELETE FROM pending_jobs WHERE id = ?;", (job_id,))
        conn.commit()
        conn.close()

    def complete_job_success(
        self,
        job_id: int,
        name: str,
        latency_reduction: float,
        score: float,
        per_problem_scores: str | None,
    ):
        """Record a completed job with status 'success' and remove it from pending."""
        conn = self._connect()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO completed_runs (
                job_id, name, latency_reduction, score, per_problem_scores, status, error_message
            )
            VALUES (?, ?, ?, ?, ?, 'success', NULL);
            """,
            (job_id, name, latency_reduction, score, per_problem_scores),
        )
        cur.execute("DELETE FROM pending_jobs WHERE id = ?;", (job_id,))
        conn.commit()
        conn.close()

    def get_leaderboard_rows(self):
        """Return (rows, pending_positions) for the leaderboard.

        rows: list of dicts with keys:
          - status: 'REGISTERING', 'PENDING', 'RUNNING', 'error', 'success', etc.
          - name
          - latency_reduction
          - score
          - per_problem_scores
          - job_id

        pending_positions: dict[job_id -> index_in_queue] for jobs still PENDING.
        """
        conn = self._connect()
        cur = conn.cursor()

        # Completed runs: best scores first (regardless of success/error).
        cur.execute(
            """
            SELECT job_id, name, latency_reduction, score, per_problem_scores, status, error_message
            FROM completed_runs
            ORDER BY score DESC, latency_reduction DESC, completed_at ASC;
            """
        )
        completed_rows = cur.fetchall()

        # Pending jobs: queue order is ascending by submission/job id.
        cur.execute(
            """
            SELECT id, name, status, submitted_at
            FROM pending_jobs
            ORDER BY id ASC;
            """
        )
        pending_rows = cur.fetchall()
        conn.close()

        rows = []
        for row in completed_rows:
            rows.append(
                {
                    "status": row["status"],
                    "name": row["name"],
                    "latency_reduction": row["latency_reduction"],
                    "score": row["score"],
                    "per_problem_scores": row["per_problem_scores"],
                    "job_id": row["job_id"],
                    "error_message": row["error_message"],
                }
            )

        for row in pending_rows:
            rows.append(
                {
                    "status": row["status"],
                    "name": row["name"],
                    "latency_reduction": None,
                    "score": None,
                    "per_problem_scores": None,
                    "job_id": row["id"],
                }
            )

        # Only jobs still PENDING contribute to the "X in queue" count.
        pending_only = [row for row in pending_rows if row["status"] == "PENDING"]
        pending_positions = {row["id"]: idx for idx, row in enumerate(pending_only)}
        return rows, pending_positions

db = Database(DB_PATH)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def parse_submission_form(req):
    """Validate and extract fields from the submission form.

    Returns:
        (name, file_storage, error_response)

    If validation fails, name and file_storage will be None and error_response
    will be a Flask response tuple (message, status_code).
    """
    name = req.form.get("name", "").strip()
    if not name:
        return None, None, ("Name is required", 400)

    if "file" not in req.files:
        return None, None, ("No file part", 400)

    file = req.files["file"]
    if file.filename == "":
        return None, None, ("No selected file", 400)

    if not allowed_file(file.filename):
        return None, None, ("Invalid file type; only .zip allowed", 400)

    return name, file, None


class HTMLBuilder:
    """Utility to build the HTML for the leaderboard page."""

    @staticmethod
    def render_leaderboard_page(rows, pending_positions=None) -> str:
        """Return full HTML given leaderboard rows.

        Each row is expected to be a mapping with keys:
        'status' ('COMPLETE' or 'PENDING'),
        'name',
        'latency_reduction',
        'score',
        and 'job_id' (only meaningful for pending rows).
        """
        if pending_positions is None:
            pending_positions = {}

        html_rows = []
        for row in rows:
            status = row["status"]
            if status == "PENDING":
                ahead = pending_positions.get(row["job_id"], 0)
                latency_str = "—"
                score_str = f"pending, {ahead} in queue"
            elif status == "RUNNING":
                latency_str = "—"
                score_str = "RUNNING NOW"
            elif status == "error":
                latency_str = "—"
                msg = row.get("error_message") or ""
                score_str = f"ERROR: {msg}"
            else:
                latency_str = (
                    f"{row['latency_reduction']:.2f}%"
                    if row["latency_reduction"] is not None
                    else "—"
                )
                if row["score"] is not None:
                    base_score_str = f"{row['score']:.3f}"
                else:
                    base_score_str = "—"

                # If we have per-problem scores, show them in a collapsible details block.
                per_problem_raw = row.get("per_problem_scores")
                details_html = ""
                if per_problem_raw:
                    try:
                        per_list = json.loads(per_problem_raw)
                        items = []
                        for p in per_list:
                            prob = p.get("problem", "?")
                            sc = p.get("score")
                            corr = p.get("correct")
                            if sc is None:
                                line = f"{prob}: ?"
                            else:
                                if corr:
                                    line = f"{prob}: {sc:.3f}"
                                else:
                                    line = f"{prob}: {sc:.3f} (FAIL)"
                            items.append(f"<li>{line}</li>")
                        items_html = "".join(items)
                        details_html = (
                            "<details><summary>per-problem</summary>"
                            "<ul>"
                            + items_html +
                            "</ul></details>"
                        )
                    except Exception:
                        details_html = ""

                if details_html:
                    score_str = base_score_str + "<br/>" + details_html
                else:
                    score_str = base_score_str

            html_rows.append(
                f"<tr>"
                f"<td>{row['name']}</td>"
                f"<td>{latency_str}</td>"
                f"<td>{score_str}</td>"
                f"</tr>"
            )
        table_body = "\n".join(html_rows) if html_rows else (
            "<tr><td colspan='3'><em>No runs submitted yet.</em></td></tr>"
        )

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Agentic SE Leaderboard</title>
            <meta charset="utf-8" />
            <style>
                body {{
                    font-family: sans-serif;
                    margin: 2rem;
                }}
                h1, h2 {{
                    margin-bottom: 0.5rem;
                }}
                form {{
                    margin-bottom: 2rem;
                    padding: 1rem;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                }}
                label {{
                    display: block;
                    margin-top: 0.5rem;
                }}
                input[type="text"], input[type="file"] {{
                    width: 100%;
                    max-width: 400px;
                    margin-top: 0.25rem;
                }}
                button {{
                    margin-top: 1rem;
                    padding: 0.5rem 1rem;
                    cursor: pointer;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    max-width: 800px;
                }}
                th, td {{
                    border: 1px solid #ccc;
                    padding: 0.5rem 0.75rem;
                    text-align: left;
                }}
                th {{
                    background-color: #f5f5f5;
                }}
            </style>
        </head>
        <body>
            <h1>Agentic SE Leaderboard</h1>

            <div style="max-width: 800px; margin-bottom: 1.5rem;">
                <h2>Instructions</h2>
                <ul>
                    <li><strong>What to submit:</strong> Upload a <code>.zip</code> file that contains only the <code>student_agent</code> folder from the template (no extra parent directory).</li>
                    <li><strong>Name field:</strong> Enter your own name and use the <em>exact same</em> name for all of your submissions so your runs stay grouped together.</li>
                    <li><strong>How scoring works:</strong> There are 10 benchmark problems. A score of about <code>10.0</code> means you match the baseline runtime on average; a score &gt; <code>10.0</code> means your agent is faster overall; a score &lt; <code>10.0</code> means it is slower. If your optimized code fails correctness on any benchmark, you receive a <code>0</code> on that one (possibly causing your score to fall well below 10).</li>
                </ul>
            </div>

            <h2>Submit a run</h2>
            <form action="submit" method="post" enctype="multipart/form-data">
                <label for="name">Your name (please use the same name for all submissions):</label>
                <input type="text" id="name" name="name" required />

                <label for="file">ZIP file:</label>
                <input type="file" id="file" name="file" accept=".zip" required />

                <button type="submit">Submit</button>
            </form>

            <h2>Leaderboard</h2>
            <table>
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Percent latency reduction</th>
                        <th>Score</th>
                    </tr>
                </thead>
                <tbody>
                    {table_body}
                </tbody>
            </table>
        </body>
        </html>
        """
        return html


# --- Runner job processing helper ---
def process_job(job, logger):
    """Process a single job: set up benchmark env, run scorer_tool, record score."""
    job_id = job["id"]
    name = job["name"]
    zip_path = job["zip_path"]

    logger.info("Runner: starting job %d for team '%s'", job_id, name)

    # Create a per-job temporary directory.
    tmp_dir = tempfile.mkdtemp(prefix=f"job-{job_id}-")
    logger.info("Runner: job %d using temp dir %s", job_id, tmp_dir)

    # Log the output of a `find` command on the student_agent_dir after extraction (to be inserted after extraction)

    # Paths for benchmark and tooling
    benchmark_src = os.path.join(BASE_DIR, "assets", "benchmarks")
    scorer_src = os.path.join(BASE_DIR, "assets", "class-materials", "scorer_tool.py")
    logger.info(
        "Runner: job %d benchmark_src=%s, scorer_src=%s, BASE_DIR=%s",
        job_id,
        benchmark_src,
        scorer_src,
        BASE_DIR,
    )

    # Select client implementation based on LLM_CLIENT_CHOICE
    if LLM_CLIENT_CHOICE == "openai":
        client_filename = "openai-client.py"
    else:
        client_filename = "ollama-client.py"

    client_src = os.path.join(
        BASE_DIR, "assets", "class-materials", "student_agent", client_filename
    )
    openai_token_path = os.path.join(BASE_DIR, "secrets", "openai.key")

    had_error = False
    try:
        # Sanity checks on benchmark + scorer
        if not os.path.isdir(benchmark_src):
            msg = f"internal error: benchmark dir not found at {benchmark_src}"
            logger.error("Runner: job %d %s", job_id, msg)
            had_error = True
            db.complete_job_with_error(job_id, name, msg)
            return

        if not os.path.isfile(scorer_src):
            msg = f"internal error: scorer_tool.py not found at {scorer_src}"
            logger.error("Runner: job %d %s", job_id, msg)
            had_error = True
            db.complete_job_with_error(job_id, name, msg)
            return

        # 1. Unpack the student submission into student_agent/
        student_agent_dir = os.path.join(tmp_dir, "student_agent")
        os.makedirs(student_agent_dir, exist_ok=True)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(student_agent_dir)
        except zipfile.BadZipFile:
            msg = "invalid zip"
            logger.warning("Runner: job %d invalid zip: %s", job_id, zip_path)
            had_error = True
            db.complete_job_with_error(job_id, name, msg)
            return
        except Exception as e:
            msg = f"invalid zip ({e})"
            logger.warning("Runner: job %d invalid zip (%s)", job_id, e)
            had_error = True
            db.complete_job_with_error(job_id, name, msg)
            return

        # Log the extracted directory structure for debugging
        try:
            find_result = subprocess.run(
                ["find", student_agent_dir, "-maxdepth", "3"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            logger.info(
                "Runner: job %d contents of student_agent_dir:\n%s",
                job_id,
                find_result.stdout,
            )
        except Exception as e:
            logger.warning(
                "Runner: job %d failed to run find on %s: %s",
                job_id,
                student_agent_dir,
                e,
            )
    
        # If the archive contained an extra top-level directory (e.g., student_agent/student_agent),
        # flatten it so that my-agent.py ends up directly under student_agent_dir.
        try:
            top_entries = os.listdir(student_agent_dir)
            # Ignore macOS metadata directories/files like __MACOSX, .DS_Store, and other dotfiles.
            visible_entries = [
                entry
                for entry in top_entries
                if not (
                    entry == "__MACOSX"
                    or entry == ".DS_Store"
                    or entry.startswith(".")
                )
            ]
            visible_paths = [
                os.path.join(student_agent_dir, entry) for entry in visible_entries
            ]
            visible_dirs = [p for p in visible_paths if os.path.isdir(p)]
            visible_files = [p for p in visible_paths if os.path.isfile(p)]

            if len(visible_dirs) == 1 and not visible_files:
                nested_dir = visible_dirs[0]
                logger.info(
                    "Runner: job %d flattening nested student_agent dir %s",
                    job_id,
                    nested_dir,
                )
                for entry in os.listdir(nested_dir):
                    src = os.path.join(nested_dir, entry)
                    dst = os.path.join(student_agent_dir, entry)
                    shutil.move(src, dst)
                os.rmdir(nested_dir)
        except Exception as e:
            logger.warning(
                "Runner: job %d failed to flatten nested student_agent dir: %s",
                job_id,
                e,
            )
        logger.info(
            "Runner: job %d student_agent_dir resolved to %s",
            job_id,
            student_agent_dir,
        )

        # 2. Confirm my-agent.py exists in student_agent/
        agent_path = os.path.join(student_agent_dir, "my-agent.py")
        if not os.path.exists(agent_path):
            msg = "missing my-agent.py"
            logger.warning("Runner: job %d %s", job_id, msg)
            had_error = True
            db.complete_job_with_error(job_id, name, msg)
            return

        # 3. Ensure appropriate client file is present in student_agent/
        client_dst = os.path.join(student_agent_dir, client_filename)
        if not os.path.exists(client_dst):
            if not os.path.exists(client_src):
                msg = (
                    f"internal error: {client_filename} not found in student_agent "
                    f"and default not found at {client_src}"
                )
                logger.error("Runner: job %d %s", job_id, msg)
                had_error = True
                db.complete_job_with_error(job_id, name, msg)
                return
            shutil.copy2(client_src, client_dst)
            logger.info(
                "Runner: job %d copied default %s into student_agent",
                job_id,
                client_filename,
            )

        # 3b. Prepare environment for scorer_tool/my-agent
        env = os.environ.copy()
        if LLM_CLIENT_CHOICE == "openai":
            # Load OpenAI token and set ECE30861_OPENAI_TOKEN
            if not os.path.exists(openai_token_path):
                msg = (
                    "internal error: OpenAI token file not found at "
                    f"{openai_token_path}"
                )
                logger.error("Runner: job %d %s", job_id, msg)
                had_error = True
                db.complete_job_with_error(job_id, name, msg)
                return
            try:
                with open(openai_token_path, "r", encoding="utf-8") as f_tok:
                    openai_token = f_tok.read().strip()
            except Exception as e:
                msg = f"failed to read OpenAI token file: {e}"
                logger.error("Runner: job %d %s", job_id, msg)
                had_error = True
                db.complete_job_with_error(job_id, name, msg)
                return
            # ECE30861_OPENAI_TOKEN: token consumed by openai-client.py
            env["ECE30861_OPENAI_TOKEN"] = openai_token

        # 4. Optional: install requirements from student_agent/requirements.txt
        req_path = os.path.join(student_agent_dir, "requirements.txt")
        if os.path.exists(req_path):
            logger.info(
                "Runner: job %d installing requirements from %s",
                job_id,
                req_path,
            )
            # Use the same Python interpreter and run pip from within student_agent_dir
            pip_cmd = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--user",
                "-r",
                req_path,
            ]
            logger.info(
                "Runner: job %d running pip with cmd=%s, cwd=%s",
                job_id,
                " ".join(pip_cmd),
                student_agent_dir,
            )
            pip_result = subprocess.run(
                pip_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=student_agent_dir,
            )
            if pip_result.returncode != 0:
                stdout_text = (pip_result.stdout or "").strip()
                stderr_text = (pip_result.stderr or "").strip()
                stdout_tail = (
                    "\n".join(stdout_text.splitlines()[-5:])
                    if stdout_text
                    else ""
                )
                stderr_tail = (
                    "\n".join(stderr_text.splitlines()[-5:])
                    if stderr_text
                    else ""
                )
                msg_parts = [
                    f"pip install failed, rc {pip_result.returncode}",
                ]
                if stdout_tail:
                    msg_parts.append(f"tail of stdout: {stdout_tail}")
                if stderr_tail:
                    msg_parts.append(f"tail of stderr: {stderr_tail}")
                msg = "; ".join(msg_parts)
                logger.warning("Runner: job %d %s", job_id, msg)
                had_error = True
                db.complete_job_with_error(job_id, name, msg)
                return

        # 5. Copy the benchmark directory into tmp_dir/local_benchmarks
        local_benchmarks_dir = os.path.join(tmp_dir, "local_benchmarks")
        try:
            shutil.copytree(benchmark_src, local_benchmarks_dir)
        except Exception as e:
            msg = f"internal error: failed to copy benchmark dir: {e}"
            logger.error("Runner: job %d %s", job_id, msg)
            had_error = True
            db.complete_job_with_error(job_id, name, msg)
            return

        # 6. Copy scorer_tool.py into tmp_dir
        scorer_dst = os.path.join(tmp_dir, "scorer_tool.py")
        try:
            shutil.copy2(scorer_src, scorer_dst)
        except Exception as e:
            msg = f"internal error: failed to copy scorer_tool.py: {e}"
            logger.error("Runner: job %d %s", job_id, msg)
            had_error = True
            db.complete_job_with_error(job_id, name, msg)
            return

        # 7. Run scorer_tool.py from inside tmp_dir
        old_cwd = os.getcwd()
        os.chdir(tmp_dir)
        try:
            scorer_cmd = [
                "python3",
                "scorer_tool.py",
                "--LLM-client",
                LLM_CLIENT_CHOICE,
                "--trials",
                "11",
            ]
            logger.info(
                "Runner: job %d invoking scorer_tool.py with %s client; cmd=%s; cwd=%s",
                job_id,
                LLM_CLIENT_CHOICE,
                " ".join(scorer_cmd),
                tmp_dir,
            )
            # For debugging, note whether ECE30861_OPENAI_TOKEN is present in env (do not log the token itself).
            has_openai = "ECE30861_OPENAI_TOKEN" in env
            logger.info(
                "Runner: job %d env has ECE30861_OPENAI_TOKEN=%s",
                job_id,
                has_openai,
            )
            result = subprocess.run(
                scorer_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=180,
                env=env,
            )
        except subprocess.TimeoutExpired:
            msg = "timeout after 180s running scorer_tool.py (job-level timeout)"
            logger.warning("Runner: job %d %s", job_id, msg)
            had_error = True
            db.complete_job_with_error(job_id, name, msg)
            return
        finally:
            try:
                os.chdir(old_cwd)
            except Exception:
                pass

        # 8. Check scorer_tool exit code
        if result.returncode != 0:
            stdout_text = (result.stdout or "").strip()
            stderr_text = (result.stderr or "").strip()

            stdout_tail = "\n".join(stdout_text.splitlines()[-5:]) if stdout_text else ""
            stderr_tail = "\n".join(stderr_text.splitlines()[-5:]) if stderr_text else ""

            msg_parts = [
                f"scorer_tool.py failed, rc {result.returncode}",
            ]
            if stdout_tail:
                msg_parts.append(f"tail of stdout: {stdout_tail}")
            else:
                msg_parts.append(f"(no stdout)")
            if stderr_tail:
                msg_parts.append(f"tail of stderr: {stderr_tail}")

            msg = "; ".join(msg_parts)

            logger.warning("Runner: job %d %s", job_id, msg)
            had_error = True
            db.complete_job_with_error(job_id, name, msg)
            return

        # 9. Parse stdout to extract TOTAL SCORE and aggregate latency reduction
        stdout_lines = result.stdout.splitlines()
        logger.info(
            "Runner: job %d scorer_tool stdout:\n%s", job_id, result.stdout
        )

        total_score_val = None
        total_starter_time = 0.0
        total_optimized_time = 0.0
        per_problem_details = []

        for line in stdout_lines:
            line = line.strip()
            if line.startswith("TOTAL SCORE:"):
                try:
                    total_score_val = float(
                        line.split("TOTAL SCORE:")[-1].strip()
                    )
                except ValueError:
                    continue
            elif "starter_time=" in line and "optimized_time=" in line:
                # Example line:
                # problem-1: starter_time=78.52ms, optimized_time=69.93ms, improvement=8.59ms, correct=True
                try:
                    # Split off the problem name (before the first colon)
                    name_part, rest = line.split(":", 1)
                    problem_name = name_part.strip()

                    st_part = rest.split("starter_time=")[1]
                    st_val_str = st_part.split("ms")[0]
                    starter_time = float(st_val_str)

                    opt_part = rest.split("optimized_time=")[1]
                    opt_val_str = opt_part.split("ms")[0]
                    optimized_time = float(opt_val_str)

                    if "improvement=" in rest:
                        imp_part = rest.split("improvement=")[1]
                        imp_val_str = imp_part.split("ms")[0]
                        improvement_ms = float(imp_val_str)
                    else:
                        improvement_ms = starter_time - optimized_time

                    correct_flag = None
                    if "correct=" in rest:
                        corr_part = rest.split("correct=")[1]
                        corr_str = corr_part.split(",")[0].strip()
                        correct_flag = corr_str.lower() == "true"

                    # Compute per-problem score consistent with scorer_tool:
                    # If correct: 1.0 + (improvement_ms / 1000.0); else 0.0
                    if correct_flag is True:
                        per_score = 1.0 + (improvement_ms / 1000.0)
                    elif correct_flag is False:
                        per_score = 0.0
                    else:
                        per_score = None

                    total_starter_time += starter_time
                    total_optimized_time += optimized_time

                    per_problem_details.append(
                        {
                            "problem": problem_name,
                            "starter_time_ms": starter_time,
                            "optimized_time_ms": optimized_time,
                            "improvement_ms": improvement_ms,
                            "correct": correct_flag,
                            "score": per_score,
                        }
                    )
                except Exception:
                    continue

        if total_score_val is None:
            msg = "failed to parse TOTAL SCORE from scorer_tool output"
            logger.warning("Runner: job %d %s", job_id, msg)
            had_error = True
            db.complete_job_with_error(job_id, name, msg)
            return

        if total_starter_time > 0.0:
            latency_reduction_pct = (
                (total_starter_time - total_optimized_time)
                / total_starter_time
                * 100.0
            )
        else:
            latency_reduction_pct = 0.0

        rounded_score = round(total_score_val, 3)
        logger.info(
            "Runner: job %d parsed score=%.3f, latency_reduction=%.2f%%",
            job_id,
            rounded_score,
            latency_reduction_pct,
        )

        # Serialize per-problem details for later debugging in the UI.
        per_problem_json = None
        if per_problem_details:
            try:
                per_problem_json = json.dumps(per_problem_details)
            except Exception as e:
                logger.warning(
                    "Runner: job %d failed to serialize per-problem details: %s",
                    job_id,
                    e,
                )
                per_problem_json = None

        # 10. Record a successful completion in the DB.
        db.complete_job_success(
            job_id=job_id,
            name=name,
            latency_reduction=latency_reduction_pct,
            score=rounded_score,
            per_problem_scores=per_problem_json,
        )

    finally:
        # Clean up temp directory only on success; keep it on error for debugging.
        if not had_error:
            try:
                shutil.rmtree(tmp_dir)
                logger.info(
                    "Runner: job %d cleaned up temp dir %s", job_id, tmp_dir
                )
            except Exception as e:
                logger.warning(
                    "Runner: job %d failed to remove temp dir %s: %s",
                    job_id,
                    tmp_dir,
                    e,
                )
        else:
            logger.info(
                "Runner: job %d encountered an error; preserving temp dir %s for debugging",
                job_id,
                tmp_dir,
            )


def runner_loop(runner_id: int):
    """Background runner: consume pending jobs and process them."""
    logger = logging.getLogger(f"runner-{runner_id}")
    logger.info("Runner %d started", runner_id)
    while True:
        try:
            job = db.fetch_next_pending_job()
        except sqlite3.OperationalError as e:
            # Handle race condition at startup where schema is not visible yet.
            if "no such table" in str(e):
                logger.warning(
                    "Runner %d: DB schema not ready yet (OperationalError: %s). Retrying...",
                    runner_id,
                    e,
                )
                time.sleep(0.5)
                continue
            else:
                raise
        if job is None:
            logger.debug("Runner %d: no pending jobs, sleeping", runner_id)
            time.sleep(1.0)
            continue

        job_id = job["id"]
        name = job["name"]
        zip_path = job["zip_path"]
        logger.info(
            "Runner %d: picked job %d for team '%s' (zip: %s)",
            runner_id,
            job_id,
            name,
            zip_path,
        )

        if not os.path.exists(zip_path):
            msg = "zip file not found on disk"
            logger.warning(
                "Runner %d: %s for job %d: %s",
                runner_id,
                msg,
                job_id,
                zip_path,
            )
            db.complete_job_with_error(job_id, name, msg)
            continue

        process_job(job, logger)

@app.route("/", methods=["GET", "POST"])
def home():
    """Render the main page with the submission form and the leaderboard.

    For deployments where only '/' is exposed, this route also accepts POST
    and delegates submission handling to submit_run().
    """
    if request.method == "POST":
        return submit_run()

    rows, pending_positions = db.get_leaderboard_rows()
    return HTMLBuilder.render_leaderboard_page(
        rows, pending_positions=pending_positions
    )


@app.route("/submit", methods=["POST"])
def submit_run():
    """Handle a run submission: save the uploaded ZIP and register a pending job.

    The actual benchmarking is done by runner.py, which will later write results
    into the `runs` table.
    """
    name, file, error = parse_submission_form(request)
    if error is not None:
        return error

    orig_filename = file.filename
    FRONTEND_LOGGER.info("Received submission from '%s' with file '%s'", name, orig_filename)

    # Step 1: Insert job in REGISTERING state with a placeholder path to get a unique job ID.
    job_id = db.insert_pending_job(name, "")

    # Step 2: Build a unique filename using the job_id prefix.
    unique_filename = f"{job_id}_{orig_filename}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], unique_filename)

    # Step 3: Save the uploaded ZIP using the unique name.
    file.save(save_path)

    # Step 4: Update the job to set the real path and transition to PENDING.
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "UPDATE pending_jobs SET zip_path = ?, status = 'PENDING' WHERE id = ?",
        (save_path, job_id),
    )
    conn.commit()
    conn.close()

    # Redirect back to the leaderboard page (external path /agents/ via nginx)
    return redirect("/agents/")


@app.route("/submissions/<path:filename>", methods=["GET"])
def download_submission(filename):
    """(Optional) Serve stored submissions, for debugging/admin use."""
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


def parse_args():
    parser = argparse.ArgumentParser(description="Agentic SE Leaderboard Server")
    parser.add_argument("--port", type=int, default=8081, help="Port to run the web server on")
    parser.add_argument("--parallelism", type=int, default=8, help="Number of runner processes")
    parser.add_argument(
        "--llmClient",
        choices=["openai", "ollama"],
        default="ollama",
        help="LLM backend to use for scoring (default: ollama)",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    LLM_CLIENT_CHOICE = args.llmClient
    db.init_schema()

    # Configure frontend logging in the parent process
    FRONTEND_LOGGER = setup_frontend_logging()
    FRONTEND_LOGGER.info(
        "Starting frontend on port %d with parallelism=%d",
        args.port,
        args.parallelism,
    )

    # Fork background runners; assign IDs 1..parallelism
    for i in range(args.parallelism):
        runner_id = i + 1
        pid = os.fork()
        if pid == 0:
            # Child process: configure its own logger and start the runner loop.
            setup_runner_logging(runner_id)
            runner_loop(runner_id)

    # Parent process: start Flask
    app.run(host="0.0.0.0", port=args.port)

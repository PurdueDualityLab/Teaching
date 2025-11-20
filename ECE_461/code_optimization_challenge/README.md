# Agentic SE Code Optimization Challenge

An automated leaderboard system for evaluating student submissions in a code optimization challenge. Students develop LLM-powered agents that automatically optimize Python code for better performance while maintaining correctness.

## Overview

This system provides a web-based leaderboard where students submit their optimization agents. The system automatically benchmarks each submission across multiple problems, measuring both runtime improvement and correctness. It supports concurrent evaluation of multiple submissions using configurable parallelism.

### Key Features

- **Automated Benchmarking**: Evaluates student agents across 10 Python optimization problems
- **LLM Integration**: Supports both OpenAI and Ollama as LLM backends
- **Parallel Processing**: Configurable number of concurrent evaluation workers
- **Real-time Leaderboard**: Web interface showing scores, latency reduction, and queue status
- **Per-Problem Breakdown**: Detailed scoring for each benchmark problem
- **Correctness Validation**: Ensures optimized code produces correct outputs

## System Architecture

The system consists of three main components:

1. **Flask Web Server** (`app.py`): Handles submission uploads and serves the leaderboard interface
2. **Worker Processes**: Background runners that fetch pending jobs and execute benchmarks
3. **Scorer Tool** (`scorer_tool.py`): Evaluates agent submissions against benchmark problems

### Workflow

1. Student uploads a `.zip` file containing their `student_agent/` folder
2. Submission is queued in SQLite database
3. A worker process picks up the job
4. Worker extracts submission, sets up benchmark environment
5. Scorer tool runs the agent on all benchmark problems
6. Results are recorded and displayed on the leaderboard

## Requirements

- Python 3.7+
- Flask
- OpenAI Python library (if using OpenAI backend)
- Ollama (if using Ollama backend)

Install dependencies:

```bash
pip install -r requirements.txt
```

## Project Structure

```
.
├── app.py                          # Main Flask application and runner orchestrator
├── clean.sh                        # Cleanup script (removes DB and logs)
├── requirements.txt                # Python dependencies
├── leaderboard.db                  # SQLite database (auto-created)
├── assets/
│   ├── benchmarks/                 # Official benchmark problems (used by server)
│   │   ├── problem-1/
│   │   │   ├── yokohama_baseline.py
│   │   │   └── cpu_1_yokohama.json
│   │   ├── problem-2/
│   │   └── ... (problem-3 through problem-9)
│   └── class-materials/            # Student-facing materials
│       ├── local_benchmarks/       # Subset of benchmarks for local testing
│       ├── student_agent/          # Agent template and LLM clients
│       │   ├── my-agent.py         # Student agent harness
│       │   ├── openai-client.py    # OpenAI LLM client
│       │   └── ollama-client.py    # Ollama LLM client
│       ├── work/                   # Example student work
│       └── scorer_tool.py          # Benchmark evaluation script
├── submissions/                    # Uploaded .zip files (auto-created)
└── logs/                           # Server and runner logs (auto-created)
```

## Setup

### Local Development

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. (Optional) Set up OpenAI API key if using OpenAI:
   ```bash
   mkdir -p secrets
   echo "your-api-key-here" > secrets/openai.key
   ```
4. Run the server:
   ```bash
   ./app.py --parallelism 4 --llmClient ollama
   ```

### Deployment

The system is designed to be deployed on a server with the following steps:

1. **Package the leaderboard**:
   ```bash
   tar -czvf leaderboard.tgz leaderboard
   ```

2. **Copy to server**:
   ```bash
   scp leaderboard.tgz davisjam@dl-berlin.ecn.purdue.edu:
   ```

3. **Extract and run on server**:
   ```bash
   ssh davisjam@berlin.ecn.purdue.edu
   rm -rf leaderboard
   tar -xzvf leaderboard.tgz
   cd leaderboard
   ./clean.sh
   ./app.py --parallelism 16 --llmClient openai
   ```

## Usage

### Running the Server

```bash
./app.py [OPTIONS]
```

**Options**:
- `--port PORT`: Port for web server (default: 8081)
- `--parallelism N`: Number of concurrent worker processes (default: 8)
- `--llmClient {openai,ollama}`: LLM backend to use (default: ollama)

**Example**:
```bash
./app.py --port 8080 --parallelism 16 --llmClient openai
```

### Student Submission Format

Students must submit a `.zip` file containing their `student_agent/` folder with:
- `my-agent.py`: The optimization agent implementation
- (Optional) `requirements.txt`: Additional Python dependencies
- (Optional) LLM client file if they modified it

The zip should NOT have an extra parent directory - `student_agent/` should be at the root of the archive.

### Scoring System

The scoring system works as follows:

- **Base Score**: Each problem starts with a score of 1.0 if correct
- **Performance Bonus**: Added based on runtime improvement: `improvement_ms / 1000.0`
- **Correctness Penalty**: Score of 0.0 if optimized code produces incorrect output
- **Total Score**: Sum of scores across all 10 problems

**Interpretation**:
- Score ≈ 10.0: Matches baseline performance
- Score > 10.0: Faster than baseline (better)
- Score < 10.0: Slower than baseline or has correctness failures

**Latency Reduction**:
- Percentage reduction in total runtime compared to baseline
- Calculated as: `(baseline_time - optimized_time) / baseline_time × 100%`

### Benchmark Problems

The system includes 9 benchmark problems covering different optimization scenarios:

1. **problem-1 (yokohama)**: Grid path counting with DFS
2. **problem-2 (max_subarray)**: Maximum subarray sum
3. **problem-3 (increasing_paths)**: Count increasing paths in grid
4. **problem-4 (wordfreq)**: Word frequency counting
5. **problem-5 (csvsum)**: CSV data summation
6. **problem-6 (logfilter)**: Log file filtering
7. **problem-7 (mixed_1_numstats)**: Mixed numeric statistics
8. **problem-8 (mixed_2_csvfilter)**: CSV filtering
9. **problem-9 (mixed_3_logprime)**: Log processing with primes

Each problem includes:
- Baseline implementation (intentionally inefficient)
- Test cases with expected outputs
- Performance benchmarks

### Viewing Results

The leaderboard is accessible at `http://localhost:8081/` (or configured port).

The interface shows:
- **Name**: Submitter name
- **Percent latency reduction**: Overall runtime improvement
- **Score**: Composite score with per-problem breakdown (expandable)
- **Status**: PENDING, RUNNING, success, or error with details

## Configuration

### Database

The system uses SQLite with two tables:
- `pending_jobs`: Queued submissions waiting for evaluation
- `completed_runs`: Finished evaluations with scores and status

### Logging

Logs are written to `logs/`:
- `frontend.log`: Web server activity
- `runner-{1..N}.log`: Individual worker logs

### Cleanup

To reset the leaderboard:

```bash
./clean.sh
```

This removes the database and all log files.

## Troubleshooting

### Common Issues

**Submission shows "missing my-agent.py"**:
- Ensure the zip file has `student_agent/my-agent.py` at the root, not nested in extra directories

**"pip install failed"**:
- Check that dependencies in student's `requirements.txt` are valid and installable
- Review runner logs for detailed pip output

**"timeout after 180s"**:
- Agent took too long to optimize (3 minute limit per submission)
- Student should optimize their agent's performance or reduce LLM calls

**Score is 0.0 on all problems**:
- Optimized code is producing incorrect outputs
- Check per-problem breakdown for specific failures

### Debugging

1. Check runner logs: `logs/runner-*.log`
2. Failed jobs preserve their temp directories for inspection
3. Use `--parallelism 1` for easier debugging
4. Test student agent locally with `scorer_tool.py` before submission

## License

For educational use in ECE 461.

## Contact

Report issues or questions through the course communication channels.

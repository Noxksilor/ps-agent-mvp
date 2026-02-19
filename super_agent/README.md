# Super Agent — Autonomous AI Task Executor

An autonomous AI agent that executes tasks using LLM + tools. Give it a task, and it will plan, iterate, and execute until done.

## Quick Start

```bash
# 1. Install dependencies
pip install -r super_agent/requirements.txt

# 2. Set your LLM API key
set ANTHROPIC_API_KEY=your-key-here
# or: set OPENAI_API_KEY=your-key-here
# or: set GOOGLE_API_KEY=your-key-here

# 3. Run the agent
python -m super_agent "Create a simple Python script that prints hello world"
```

## Usage

### Single Task Mode

```bash
python -m super_agent "Your task description here"
```

### Interactive Mode (REPL)

```bash
python -m super_agent --interactive
```

### With Custom Config

```bash
python -m super_agent --config super_agent/example_config.json "Your task"
```

## Configuration

Configuration is loaded from (in order of priority):
1. Environment variables
2. Config file (JSON)
3. Default values

### Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | API key for Claude |
| `OPENAI_API_KEY` | API key for GPT-4 |
| `GOOGLE_API_KEY` | API key for Gemini |
| `AGENT_WORKING_DIR` | Working directory |
| `AGENT_LOG_DIR` | Log directory |
| `AGENT_MAX_ITERATIONS` | Max iterations (default: 50) |
| `N8N_BASE_URL` | n8n base URL |
| `PS_AGENT_DIR` | ps-agent-mvp directory |

### Config File

See [`example_config.json`](example_config.json) for all options.

## Available Tools

The agent has access to these tools:

| Tool | Description |
|------|-------------|
| `read_file` | Read a file's contents |
| `write_file` | Write content to a file |
| `list_dir` | List directory contents |
| `delete_file` | Delete a file or directory |
| `run_command` | Run a shell command |
| `http_request` | Make an HTTP request |
| `web_search` | Search the web (DuckDuckGo) |
| `ps_agent_run` | Run the ps-agent-mvp pipeline |
| `n8n_list_workflows` | List n8n workflows |
| `n8n_run_workflow` | Execute an n8n workflow |

## Security

- Only whitelisted commands can be executed (see `allowed_commands` in config)
- File operations are restricted to `working_dir` by default
- No tasks are started without user input

## Logs

Logs are written to `agent_logs/` with timestamps:
- `agent_YYYYMMDD_HHMMSS.log` — Full execution log

## Examples

### Run ps-agent-mvp pipeline

```bash
python -m super_agent "Run the ps-agent-mvp pipeline with configjson/example_job.json and report the result"
```

### Create a new project

```bash
python -m super_agent "Create a new Flask project in my_project/ with a /hello endpoint"
```

### Work with n8n

```bash
python -m super_agent "List all n8n workflows and tell me which ones are active"
```

## Architecture

```
super_agent/
├── __init__.py      # Package init
├── __main__.py      # Entry point for python -m
├── cli.py           # Command-line interface
├── config.py        # Configuration management
├── agent.py         # Core agent logic
├── tools.py         # Tool implementations
├── requirements.txt # Dependencies
└── example_config.json
```

## How It Works

1. **Task Input**: User provides a task via CLI or interactive mode
2. **Planning**: LLM analyzes the task and plans steps
3. **Execution**: Agent calls tools to execute each step
4. **Iteration**: Results are fed back to LLM for next step
5. **Completion**: Agent reports success or blocker

The agent iterates until:
- Task is complete (`TASK_COMPLETE:`)
- Task is blocked (`TASK_BLOCKED:`)
- Max iterations reached (default: 50)

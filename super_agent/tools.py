"""
super_agent/tools.py — Tool implementations for the agent

Each tool is a function that takes parameters and returns a result dict:
{
    "success": bool,
    "output": str,      # Human-readable output
    "error": str,       # Error message if failed
    "data": any,        # Structured data (optional)
}
"""

import os
import re
import json
import shutil
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable


def tool_read_file(params: dict, config) -> dict:
    """Read a file's contents."""
    path = params.get("path", "")
    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = Path(config.working_dir) / path
        
        if not file_path.exists():
            return {"success": False, "error": f"File not found: {file_path}"}
        
        content = file_path.read_text(encoding="utf-8")
        lines = content.splitlines()
        
        # Limit output size
        if len(lines) > 500:
            return {
                "success": True,
                "output": f"File: {file_path} ({len(lines)} lines)\n--- First 200 lines ---\n" + 
                          "\n".join(lines[:200]) + f"\n... ({len(lines) - 200} more lines)",
                "data": {"path": str(file_path), "lines": len(lines)}
            }
        
        return {
            "success": True,
            "output": f"File: {file_path} ({len(lines)} lines)\n" + content,
            "data": {"path": str(file_path), "lines": len(lines)}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_write_file(params: dict, config) -> dict:
    """Write content to a file."""
    path = params.get("path", "")
    content = params.get("content", "")
    append = params.get("append", False)
    
    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = Path(config.working_dir) / path
        
        # Create parent directories
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        mode = "a" if append else "w"
        with open(file_path, mode, encoding="utf-8") as f:
            f.write(content)
        
        return {
            "success": True,
            "output": f"Wrote {len(content)} chars to {file_path}",
            "data": {"path": str(file_path), "size": len(content)}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_list_dir(params: dict, config) -> dict:
    """List directory contents."""
    path = params.get("path", ".")
    recursive = params.get("recursive", False)
    
    try:
        dir_path = Path(path)
        if not dir_path.is_absolute():
            dir_path = Path(config.working_dir) / path
        
        if not dir_path.exists():
            return {"success": False, "error": f"Directory not found: {dir_path}"}
        
        items = []
        if recursive:
            for item in dir_path.rglob("*"):
                rel = item.relative_to(dir_path)
                items.append(f"{'[DIR] ' if item.is_dir() else '      '}{rel}")
        else:
            for item in sorted(dir_path.iterdir()):
                items.append(f"{'[DIR] ' if item.is_dir() else '      '}{item.name}")
        
        return {
            "success": True,
            "output": f"Directory: {dir_path}\n" + "\n".join(items[:100]) + 
                      (f"\n... ({len(items) - 100} more)" if len(items) > 100 else ""),
            "data": {"path": str(dir_path), "count": len(items)}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_delete_file(params: dict, config) -> dict:
    """Delete a file or directory."""
    path = params.get("path", "")
    
    try:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = Path(config.working_dir) / path
        
        if not file_path.exists():
            return {"success": False, "error": f"Path not found: {file_path}"}
        
        if file_path.is_dir():
            shutil.rmtree(file_path)
            return {"success": True, "output": f"Deleted directory: {file_path}"}
        else:
            file_path.unlink()
            return {"success": True, "output": f"Deleted file: {file_path}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_run_command(params: dict, config) -> dict:
    """Run a shell command."""
    command = params.get("command", "")
    cwd = params.get("cwd", config.working_dir)
    timeout = params.get("timeout", 60)
    
    if not command:
        return {"success": False, "error": "No command specified"}
    
    # Security check: only allow certain commands
    cmd_parts = command.split()
    if cmd_parts:
        base_cmd = cmd_parts[0].lower()
        # Check if command is in allowed list (or is a path to an allowed command)
        allowed = False
        for allowed_cmd in config.allowed_commands:
            if base_cmd == allowed_cmd or base_cmd.endswith(f"/{allowed_cmd}") or base_cmd.endswith(f"\\{allowed_cmd}"):
                allowed = True
                break
        
        if not allowed and not base_cmd.startswith("."):
            return {
                "success": False,
                "error": f"Command not allowed: {base_cmd}. Allowed: {config.allowed_commands}"
            }
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"
        
        # Truncate long output
        if len(output) > 5000:
            output = output[:5000] + f"\n... (truncated, {len(output)} total chars)"
        
        return {
            "success": result.returncode == 0,
            "output": f"$ {command}\n{output}",
            "data": {"returncode": result.returncode}
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_http_request(params: dict, config) -> dict:
    """Make an HTTP request."""
    url = params.get("url", "")
    method = params.get("method", "GET").upper()
    headers = params.get("headers", {})
    body = params.get("body")
    timeout = params.get("timeout", 30)
    
    if not url:
        return {"success": False, "error": "No URL specified"}
    
    try:
        req = urllib.request.Request(url, method=method)
        for key, value in headers.items():
            req.add_header(key, value)
        
        if body and method in ("POST", "PUT", "PATCH"):
            if isinstance(body, dict):
                body = json.dumps(body).encode("utf-8")
                req.add_header("Content-Type", "application/json")
            else:
                body = body.encode("utf-8")
        
        with urllib.request.urlopen(req, body, timeout=timeout) as response:
            response_body = response.read().decode("utf-8")
            
            # Try to parse as JSON
            try:
                data = json.loads(response_body)
                output = json.dumps(data, indent=2, ensure_ascii=False)
            except:
                output = response_body
            
            # Truncate
            if len(output) > 5000:
                output = output[:5000] + f"\n... (truncated)"
            
            return {
                "success": True,
                "output": f"{method} {url}\nStatus: {response.status}\n\n{output}",
                "data": {"status": response.status}
            }
    except urllib.error.HTTPError as e:
        return {
            "success": False,
            "error": f"HTTP {e.code}: {e.reason}",
            "data": {"status": e.code}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_web_search(params: dict, config) -> dict:
    """Search the web (using DuckDuckGo instant answer API - no API key needed)."""
    query = params.get("query", "")
    
    if not query:
        return {"success": False, "error": "No search query specified"}
    
    if not config.web_search_enabled:
        return {"success": False, "error": "Web search is disabled in config"}
    
    try:
        # Use DuckDuckGo instant answer API
        url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json&no_html=1"
        
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        results = []
        
        # Abstract
        if data.get("AbstractText"):
            results.append(f"Summary: {data['AbstractText']}")
            if data.get("AbstractURL"):
                results.append(f"Source: {data['AbstractURL']}")
        
        # Related topics
        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append(f"- {topic['Text']}")
        
        if not results:
            results.append("No results found. Try a different query.")
        
        return {
            "success": True,
            "output": f"Search: {query}\n\n" + "\n".join(results),
            "data": {"query": query}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_ps_agent_run(params: dict, config) -> dict:
    """Run the ps-agent-mvp pipeline."""
    job_config = params.get("config", "configjson/example_job.json")
    
    try:
        ps_dir = Path(config.ps_agent_dir)
        if not ps_dir.exists():
            return {"success": False, "error": f"ps-agent-mvp directory not found: {ps_dir}"}
        
        orchestrator = ps_dir / "orchestrator.py"
        if not orchestrator.exists():
            return {"success": False, "error": f"orchestrator.py not found: {orchestrator}"}
        
        # Run the pipeline
        result = subprocess.run(
            ["python", str(orchestrator), job_config],
            cwd=str(ps_dir),
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"
        
        return {
            "success": result.returncode == 0,
            "output": f"ps-agent-mvp: {job_config}\n{output}",
            "data": {"returncode": result.returncode}
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "ps-agent-mvp timed out after 5 minutes"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_n8n_list_workflows(params: dict, config) -> dict:
    """List n8n workflows."""
    try:
        url = f"{config.n8n_base_url}/api/v1/workflows"
        headers = {}
        if config.n8n_api_key:
            headers["X-N8N-API-KEY"] = config.n8n_api_key
        
        req = urllib.request.Request(url)
        for key, value in headers.items():
            req.add_header(key, value)
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        workflows = data.get("data", data)
        lines = []
        for wf in workflows:
            status = "active" if wf.get("active") else "inactive"
            lines.append(f"[{status}] {wf.get('name', 'unnamed')} (id: {wf.get('id')})")
        
        return {
            "success": True,
            "output": "n8n Workflows:\n" + "\n".join(lines),
            "data": {"workflows": workflows}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def tool_n8n_run_workflow(params: dict, config) -> dict:
    """Execute an n8n workflow (via webhook or manual trigger)."""
    workflow_id = params.get("workflow_id")
    webhook_url = params.get("webhook_url")
    payload = params.get("payload", {})
    
    try:
        # If webhook URL provided, use that
        if webhook_url:
            url = webhook_url
        elif workflow_id:
            # Try to trigger via webhook path pattern
            url = f"{config.n8n_base_url}/webhook/{workflow_id}"
        else:
            return {"success": False, "error": "Provide workflow_id or webhook_url"}
        
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req, timeout=30) as response:
            data = response.read().decode("utf-8")
            try:
                parsed = json.loads(data)
                output = json.dumps(parsed, indent=2)
            except:
                output = data
        
        return {
            "success": True,
            "output": f"Triggered: {url}\n{output}",
            "data": {"url": url}
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


# Tool registry
TOOLS: Dict[str, Callable] = {
    "read_file": tool_read_file,
    "write_file": tool_write_file,
    "list_dir": tool_list_dir,
    "delete_file": tool_delete_file,
    "run_command": tool_run_command,
    "http_request": tool_http_request,
    "web_search": tool_web_search,
    "ps_agent_run": tool_ps_agent_run,
    "n8n_list_workflows": tool_n8n_list_workflows,
    "n8n_run_workflow": tool_n8n_run_workflow,
}


def get_tool_descriptions() -> str:
    """Get descriptions of all available tools for the LLM."""
    descriptions = []
    for name, func in TOOLS.items():
        doc = func.__doc__ or "No description"
        descriptions.append(f"- {name}: {doc.strip()}")
    return "\n".join(descriptions)


def execute_tool(tool_name: str, params: dict, config) -> dict:
    """Execute a tool by name."""
    if tool_name not in TOOLS:
        return {"success": False, "error": f"Unknown tool: {tool_name}"}
    
    return TOOLS[tool_name](params, config)

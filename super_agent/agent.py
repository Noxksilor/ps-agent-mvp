"""
super_agent/agent.py — Core agent implementation

The agent:
1. Receives a task from the user
2. Plans steps using an LLM
3. Executes tools to accomplish the task
4. Iterates until done or max iterations reached
5. Reports progress and final result
"""

import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from .config import Config
from .tools import execute_tool, get_tool_descriptions, TOOLS


# System prompt for the LLM
SYSTEM_PROMPT = """You are an autonomous AI agent that executes tasks using tools.

Your behavior:
1. You receive a task from the user
2. You plan and execute steps using the available tools
3. You iterate until the task is complete or you hit a clear blocker
4. You report progress after each step

IMPORTANT RULES:
- Only use the tools listed below - do not make up tools
- Each tool call must be valid JSON with "tool" and "params" keys
- If a tool fails, analyze the error and try a different approach
- When the task is complete, respond with "TASK_COMPLETE:" followed by a summary
- If you cannot complete the task, respond with "TASK_BLOCKED:" followed by the reason
- Do NOT start new tasks - only work on the given task

Available tools:
{tool_descriptions}

Response format:
For each step, respond with a JSON object containing:
1. "thought": Your reasoning about what to do next
2. "tool": The tool to call (or null if done)
3. "params": Parameters for the tool (or null)
4. "status": "working", "complete", or "blocked"

Example:
{
  "thought": "I need to read the config file to understand the project structure",
  "tool": "read_file",
  "params": {"path": "config.json"},
  "status": "working"
}
"""


class SuperAgent:
    """Autonomous agent that executes tasks using LLM + tools."""
    
    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config.load()
        self.logger = self._setup_logger()
        self.history: List[Dict[str, Any]] = []
        self.iteration = 0
        
        # Initialize LLM client
        self.llm_client = None
        self._init_llm_client()
    
    def _setup_logger(self) -> logging.Logger:
        """Set up logging."""
        log_dir = Path(self.config.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = log_dir / f"agent_{timestamp}.log"
        
        logger = logging.getLogger("super_agent")
        logger.setLevel(logging.DEBUG)
        
        # File handler
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(message)s"
        ))
        logger.addHandler(fh)
        
        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(asctime)s | %(message)s", datefmt="%H:%M:%S"))
        logger.addHandler(ch)
        
        return logger
    
    def _init_llm_client(self):
        """Initialize the LLM client based on provider."""
        provider = self.config.llm_provider
        
        if provider == "anthropic":
            try:
                import anthropic
                self.llm_client = anthropic.Anthropic(api_key=self.config.llm_api_key)
                self.logger.info(f"Initialized Anthropic client (model: {self.config.llm_model})")
            except ImportError:
                self.logger.error("anthropic package not installed. Run: pip install anthropic")
                raise
        elif provider == "openai":
            try:
                import openai
                self.llm_client = openai.OpenAI(api_key=self.config.llm_api_key)
                self.logger.info(f"Initialized OpenAI client (model: {self.config.llm_model})")
            except ImportError:
                self.logger.error("openai package not installed. Run: pip install openai")
                raise
        elif provider == "google":
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.config.llm_api_key)
                self.llm_client = genai.GenerativeModel(self.config.llm_model)
                self.logger.info(f"Initialized Google client (model: {self.config.llm_model})")
            except ImportError:
                self.logger.error("google-generativeai package not installed. Run: pip install google-generativeai")
                raise
        else:
            raise ValueError(f"Unknown LLM provider: {provider}")
    
    def _call_llm(self, messages: List[Dict[str, str]]) -> str:
        """Call the LLM with messages and return the response."""
        provider = self.config.llm_provider
        
        if provider == "anthropic":
            response = self.llm_client.messages.create(
                model=self.config.llm_model,
                max_tokens=self.config.llm_max_tokens,
                temperature=self.config.llm_temperature,
                system=SYSTEM_PROMPT.format(tool_descriptions=get_tool_descriptions()),
                messages=messages
            )
            return response.content[0].text
        
        elif provider == "openai":
            response = self.llm_client.chat.completions.create(
                model=self.config.llm_model,
                max_tokens=self.config.llm_max_tokens,
                temperature=self.config.llm_temperature,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT.format(tool_descriptions=get_tool_descriptions())},
                    *messages
                ]
            )
            return response.choices[0].message.content
        
        elif provider == "google":
            # Google uses a different API
            full_prompt = SYSTEM_PROMPT.format(tool_descriptions=get_tool_descriptions())
            for msg in messages:
                if msg["role"] == "user":
                    full_prompt += f"\n\nUser: {msg['content']}"
                elif msg["role"] == "assistant":
                    full_prompt += f"\n\nAssistant: {msg['content']}"
            
            response = self.llm_client.generate_content(full_prompt)
            return response.text
        
        raise ValueError(f"Unknown provider: {provider}")
    
    def _parse_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into structured data."""
        # Try to extract JSON from the response
        try:
            # Look for JSON object
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        # Check for completion markers
        if "TASK_COMPLETE:" in response:
            return {
                "thought": response,
                "tool": None,
                "params": None,
                "status": "complete"
            }
        
        if "TASK_BLOCKED:" in response:
            return {
                "thought": response,
                "tool": None,
                "params": None,
                "status": "blocked"
            }
        
        # Default: treat as thought only
        return {
            "thought": response,
            "tool": None,
            "params": None,
            "status": "working"
        }
    
    def run(self, task: str) -> Dict[str, Any]:
        """
        Execute a task autonomously.
        
        Args:
            task: The task description
            
        Returns:
            Result dict with status, summary, and history
        """
        self.logger.info("=" * 60)
        self.logger.info(f"TASK: {task}")
        self.logger.info("=" * 60)
        
        messages = [
            {"role": "user", "content": f"Task: {task}\n\nBegin by planning your approach, then execute step by step."}
        ]
        
        result = {
            "task": task,
            "status": "unknown",
            "summary": "",
            "iterations": 0,
            "history": []
        }
        
        while self.iteration < self.config.max_iterations:
            self.iteration += 1
            self.logger.info(f"\n--- Iteration {self.iteration} ---")
            
            try:
                # Call LLM
                response = self._call_llm(messages)
                self.logger.debug(f"LLM response: {response[:500]}...")
                
                # Parse response
                parsed = self._parse_response(response)
                thought = parsed.get("thought", "")
                tool = parsed.get("tool")
                params = parsed.get("params") or {}
                status = parsed.get("status", "working")
                
                self.logger.info(f"Thought: {thought[:200]}...")
                
                # Record in history
                step_record = {
                    "iteration": self.iteration,
                    "thought": thought,
                    "tool": tool,
                    "params": params,
                    "status": status
                }
                
                # Execute tool if specified
                if tool:
                    self.logger.info(f"Tool: {tool}({params})")
                    tool_result = execute_tool(tool, params, self.config)
                    step_record["tool_result"] = tool_result
                    
                    success = tool_result.get("success", False)
                    output = tool_result.get("output", tool_result.get("error", ""))
                    
                    self.logger.info(f"Result: {'OK' if success else 'FAILED'}")
                    if not success:
                        self.logger.warning(f"Error: {output[:200]}")
                    
                    # Add to messages for next iteration
                    messages.append({"role": "assistant", "content": response})
                    messages.append({
                        "role": "user",
                        "content": f"Tool result:\n{output}\n\nContinue with the next step."
                    })
                else:
                    # No tool - check status
                    if status == "complete" or "TASK_COMPLETE:" in thought:
                        result["status"] = "complete"
                        result["summary"] = thought.replace("TASK_COMPLETE:", "").strip()
                        self.logger.info(f"\n{'=' * 60}")
                        self.logger.info("TASK COMPLETE")
                        self.logger.info(result["summary"])
                        break
                    
                    if status == "blocked" or "TASK_BLOCKED:" in thought:
                        result["status"] = "blocked"
                        result["summary"] = thought.replace("TASK_BLOCKED:", "").strip()
                        self.logger.error(f"\nTASK BLOCKED: {result['summary']}")
                        break
                    
                    # Continue conversation
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": "Continue with the next step."})
                
                result["history"].append(step_record)
                
            except Exception as e:
                self.logger.error(f"Error in iteration {self.iteration}: {e}")
                result["status"] = "error"
                result["summary"] = str(e)
                break
        
        if self.iteration >= self.config.max_iterations:
            result["status"] = "max_iterations"
            result["summary"] = f"Reached maximum iterations ({self.config.max_iterations})"
            self.logger.warning(result["summary"])
        
        result["iterations"] = self.iteration
        
        self.logger.info("\n" + "=" * 60)
        self.logger.info(f"FINAL STATUS: {result['status'].upper()}")
        self.logger.info("=" * 60)
        
        return result


def run_agent(task: str, config: Optional[Config] = None) -> Dict[str, Any]:
    """
    Convenience function to run the agent.
    
    Args:
        task: The task description
        config: Optional configuration
        
    Returns:
        Result dict
    """
    agent = SuperAgent(config)
    return agent.run(task)

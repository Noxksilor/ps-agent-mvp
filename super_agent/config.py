"""
super_agent/config.py — Configuration management

The agent reads configuration from:
1. Environment variables (highest priority)
2. config.json in the working directory
3. Default values
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class Config:
    """Agent configuration."""
    
    # LLM settings
    llm_provider: str = "anthropic"  # anthropic, openai, google
    llm_model: str = "claude-sonnet-4-20250514"
    llm_api_key: Optional[str] = None
    llm_max_tokens: int = 4096
    llm_temperature: float = 0.7
    
    # Agent behavior
    max_iterations: int = 50
    working_dir: str = "."
    log_dir: str = "agent_logs"
    
    # Tool permissions
    allowed_commands: List[str] = field(default_factory=lambda: [
        "python", "pip", "git", "docker", "docker-compose",
        "npm", "node", "curl", "wget"
    ])
    allowed_paths: List[str] = field(default_factory=lambda: ["."])
    
    # External services
    notion_api_key: Optional[str] = None
    notion_database_id: Optional[str] = None
    web_search_enabled: bool = True
    
    # n8n integration
    n8n_base_url: str = "http://localhost:5678"
    n8n_api_key: Optional[str] = None
    
    # ps-agent-mvp
    ps_agent_dir: str = "C:/ps_jobs/job_0001"
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "Config":
        """Load configuration from file and environment."""
        config = cls()
        
        # Try to load from config file
        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key, value in data.items():
                    if hasattr(config, key):
                        setattr(config, key, value)
        
        # Override with environment variables
        env_mappings = {
            "ANTHROPIC_API_KEY": "llm_api_key",
            "OPENAI_API_KEY": "llm_api_key",
            "GOOGLE_API_KEY": "llm_api_key",
            "NOTION_API_KEY": "notion_api_key",
            "NOTION_DATABASE_ID": "notion_database_id",
            "N8N_API_KEY": "n8n_api_key",
            "N8N_BASE_URL": "n8n_base_url",
            "PS_AGENT_DIR": "ps_agent_dir",
            "AGENT_WORKING_DIR": "working_dir",
            "AGENT_LOG_DIR": "log_dir",
            "AGENT_MAX_ITERATIONS": "max_iterations",
        }
        
        for env_var, config_key in env_mappings.items():
            value = os.environ.get(env_var)
            if value:
                if config_key in ("max_iterations",):
                    value = int(value)
                setattr(config, config_key, value)
        
        # Auto-detect LLM provider from API key
        if not config.llm_api_key:
            if os.environ.get("ANTHROPIC_API_KEY"):
                config.llm_provider = "anthropic"
                config.llm_api_key = os.environ["ANTHROPIC_API_KEY"]
            elif os.environ.get("OPENAI_API_KEY"):
                config.llm_provider = "openai"
                config.llm_model = "gpt-4o"
                config.llm_api_key = os.environ["OPENAI_API_KEY"]
            elif os.environ.get("GOOGLE_API_KEY"):
                config.llm_provider = "google"
                config.llm_model = "gemini-1.5-pro"
                config.llm_api_key = os.environ["GOOGLE_API_KEY"]
        
        return config
    
    def to_dict(self) -> dict:
        """Convert to dictionary (for logging/debugging)."""
        return {
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "llm_api_key": "***" if self.llm_api_key else None,
            "max_iterations": self.max_iterations,
            "working_dir": self.working_dir,
            "log_dir": self.log_dir,
            "n8n_base_url": self.n8n_base_url,
            "ps_agent_dir": self.ps_agent_dir,
        }

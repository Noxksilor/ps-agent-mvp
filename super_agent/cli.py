#!/usr/bin/env python
"""
super_agent/cli.py — Command-line interface for the super-agent

Usage:
    python -m super_agent "Your task description here"
    python -m super_agent --config agent_config.json "Your task"
    python -m super_agent --interactive
"""

import sys
import argparse
from pathlib import Path

from .config import Config
from .agent import SuperAgent


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous AI agent for task execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m super_agent "Create a simple Flask app with a /hello endpoint"
    python -m super_agent --config my_config.json "Run the ps-agent pipeline"
    python -m super_agent --interactive
        """
    )
    
    parser.add_argument(
        "task",
        nargs="?",
        help="The task for the agent to execute"
    )
    
    parser.add_argument(
        "--config", "-c",
        help="Path to configuration file (JSON)"
    )
    
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Start interactive mode (enter tasks in a REPL)"
    )
    
    parser.add_argument(
        "--working-dir", "-w",
        default=".",
        help="Working directory for the agent (default: current directory)"
    )
    
    parser.add_argument(
        "--max-iterations", "-m",
        type=int,
        default=50,
        help="Maximum number of iterations (default: 50)"
    )
    
    parser.add_argument(
        "--log-dir", "-l",
        default="agent_logs",
        help="Directory for log files (default: agent_logs)"
    )
    
    args = parser.parse_args()
    
    # Load configuration
    config = Config.load(args.config)
    
    # Override with CLI args
    if args.working_dir:
        config.working_dir = str(Path(args.working_dir).resolve())
    if args.max_iterations:
        config.max_iterations = args.max_iterations
    if args.log_dir:
        config.log_dir = args.log_dir
    
    # Check for API key
    if not config.llm_api_key:
        print("ERROR: No LLM API key found.")
        print("\nSet one of these environment variables:")
        print("  ANTHROPIC_API_KEY=your-key  (for Claude)")
        print("  OPENAI_API_KEY=your-key     (for GPT-4)")
        print("  GOOGLE_API_KEY=your-key     (for Gemini)")
        print("\nOr create a config file with 'llm_api_key'.")
        sys.exit(1)
    
    # Interactive mode
    if args.interactive:
        print("=" * 60)
        print("  Super Agent — Interactive Mode")
        print("=" * 60)
        print(f"  Provider: {config.llm_provider}")
        print(f"  Model: {config.llm_model}")
        print(f"  Working dir: {config.working_dir}")
        print("=" * 60)
        print("  Type your task and press Enter. Type 'exit' to quit.")
        print("=" * 60)
        
        agent = SuperAgent(config)
        
        while True:
            try:
                task = input("\nTask> ").strip()
                if not task:
                    continue
                if task.lower() in ("exit", "quit", "q"):
                    print("Goodbye!")
                    break
                
                result = agent.run(task)
                print(f"\n[{result['status'].upper()}] {result['summary']}")
                
            except KeyboardInterrupt:
                print("\nInterrupted. Type 'exit' to quit.")
            except EOFError:
                break
        
        return
    
    # Single task mode
    if not args.task:
        parser.print_help()
        print("\nERROR: No task specified. Use --interactive for REPL mode.")
        sys.exit(1)
    
    # Run the agent
    agent = SuperAgent(config)
    result = agent.run(args.task)
    
    print("\n" + "=" * 60)
    print(f"  STATUS: {result['status'].upper()}")
    print("=" * 60)
    print(result['summary'])
    print(f"\nIterations: {result['iterations']}")
    
    # Exit with appropriate code
    if result['status'] == 'complete':
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

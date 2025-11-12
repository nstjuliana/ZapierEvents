#!/usr/bin/env python3
"""
Local development server runner.

Runs the FastAPI application using uvicorn for fast local development.
Much faster than SAM Local since it doesn't use Docker containers.

Usage:
    python run_local.py
    python run_local.py --port 8000
    python run_local.py --reload  # Auto-reload on code changes
"""

import argparse
import sys
import os
from pathlib import Path

project_root = Path(__file__).parent
src_path = project_root / "src"

try:
    import uvicorn
except ImportError:
    print("ERROR: uvicorn is not installed.")
    print("Please install dependencies: pip install -r requirements.txt")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Run FastAPI application locally with uvicorn"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on (default: 8000)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes (recommended for development)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["critical", "error", "warning", "info", "debug", "trace"],
        help="Log level for uvicorn (default: info)"
    )

    args = parser.parse_args()

    # Check if .env file exists
    env_file = project_root / ".env"
    if not env_file.exists():
        print("WARNING: .env file not found!")
        print("Creating .env from .env.example...")
        env_example = project_root / ".env.example"
        if env_example.exists():
            import shutil
            shutil.copy(env_example, env_file)
            print(f"Created .env file. Please edit it with your configuration.")
        else:
            print("ERROR: .env.example not found. Please create a .env file manually.")
            print("Required environment variables:")
            print("  - EVENTS_TABLE_NAME")
            print("  - API_KEYS_TABLE_NAME")
            print("  - INBOX_QUEUE_URL")
            print("  - ZAPIER_WEBHOOK_URL")
            sys.exit(1)

    print("=" * 60)
    print("Starting Zapier Triggers API (Local Development)")
    print("=" * 60)
    print(f"Server: http://{args.host}:{args.port}")
    print(f"API Docs: http://{args.host}:{args.port}/docs")
    print(f"ReDoc: http://{args.host}:{args.port}/redoc")
    print(f"Health: http://{args.host}:{args.port}/health")
    print("=" * 60)
    if args.reload:
        print("Auto-reload: ENABLED (code changes will restart server)")
    print()

    # Run uvicorn
    # Stay in project root so .env file loads correctly
    # Use src.main:app as the module path
    uvicorn.run(
        "src.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
        reload_dirs=[str(project_root / "src")] if args.reload else None
    )


if __name__ == "__main__":
    main()


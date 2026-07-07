"""
Local MCP server exposing file system and shell tools.

Run:
    python -m local_mcp.server                # streamable-http on :8765
    python -m local_mcp.server --stdio        # stdio transport
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

from dotenv import load_dotenv

load_dotenv()

# ── Telemetry bootstrap (must happen before trace.get_tracer) ─────────────
import sys as _sys
import pathlib as _pathlib
_sys.path.insert(0, str(_pathlib.Path(__file__).parent.parent))
from harness.telemetry import setup_telemetry_from_env
setup_telemetry_from_env(service_name="local-mcp")

try:
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode
    tracer = trace.get_tracer(__name__)
    _otel_available = True
except ImportError:
    tracer = None  # type: ignore[assignment]
    _otel_available = False

# ── MCP server ────────────────────────────────────────────────────────────
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

mcp = FastMCP(
    name="local-tools",
    instructions="File system and shell execution tools running on the local machine.",
    host="127.0.0.1",
    port=8765,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False,
    ),
)

_MAX_OUTPUT = 50_000
_CAPTURE_CONTENT = os.environ.get("OTEL_CAPTURE_CONTENT", "false").lower() == "true"


@mcp.tool()
def read_file(path: str) -> str:
    """Read the UTF-8 text content of a file.

    :param path: Path to the file (relative to cwd or absolute).
    :type path: str
    :return: File content as text, or a JSON error object.
    :rtype: str
    """
    with tracer.start_as_current_span("mcp.read_file") as span:
        if _otel_available and span.is_recording():
            span.set_attribute("rpc.method", "read_file")
            if _CAPTURE_CONTENT:
                span.set_attribute("mcp.tool.argument.path", path)
        try:
            return pathlib.Path(path).read_text(encoding="utf-8")
        except Exception as exc:
            if _otel_available and span.is_recording():
                span.set_status(StatusCode.ERROR, str(exc))
            return json.dumps({"error": str(exc)})


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """Write UTF-8 text to a file, creating parent directories as needed.

    :param path: Destination path.
    :type path: str
    :param content: Text content to write.
    :type content: str
    :return: Confirmation message, or a JSON error object.
    :rtype: str
    """
    with tracer.start_as_current_span("mcp.write_file") as span:
        if _otel_available and span.is_recording():
            span.set_attribute("rpc.method", "write_file")
            if _CAPTURE_CONTENT:
                span.set_attribute("mcp.tool.argument.path", path)
                span.set_attribute("mcp.tool.argument.content_length", len(content))
        try:
            p = pathlib.Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} chars to {path}"
        except Exception as exc:
            if _otel_available and span.is_recording():
                span.set_status(StatusCode.ERROR, str(exc))
            return json.dumps({"error": str(exc)})


@mcp.tool()
def list_files(directory: str = ".", glob_pattern: str = "**/*") -> str:
    """List files in a directory matching a glob pattern.

    :param directory: Root directory to search. Defaults to current directory.
    :type directory: str
    :param glob_pattern: Glob pattern. Defaults to all files recursively.
    :type glob_pattern: str
    :return: JSON array of matching file paths, or a JSON error object.
    :rtype: str
    """
    with tracer.start_as_current_span("mcp.list_files") as span:
        if _otel_available and span.is_recording():
            span.set_attribute("rpc.method", "list_files")
            if _CAPTURE_CONTENT:
                span.set_attribute("mcp.tool.argument.directory", directory)
                span.set_attribute("mcp.tool.argument.glob_pattern", glob_pattern)
        try:
            root = pathlib.Path(directory)
            files = sorted(str(p) for p in root.glob(glob_pattern) if p.is_file())
            if _otel_available and span.is_recording():
                span.set_attribute("mcp.tool.result.file_count", len(files))
            return json.dumps(files)
        except Exception as exc:
            if _otel_available and span.is_recording():
                span.set_status(StatusCode.ERROR, str(exc))
            return json.dumps({"error": str(exc)})


@mcp.tool()
def run_shell(
    command: str,
    working_dir: str = ".",
    timeout_seconds: int = 30,
) -> str:
    """Execute a shell command and return its output.

    The command is passed to /bin/sh -c. stdout and stderr are captured.

    :param command: Shell command string to execute.
    :type command: str
    :param working_dir: Working directory. Defaults to current directory.
    :type working_dir: str
    :param timeout_seconds: Execution timeout in seconds. Defaults to 30.
    :type timeout_seconds: int
    :return: JSON object with stdout, stderr, and return_code; or error.
    :rtype: str
    """
    with tracer.start_as_current_span("mcp.run_shell") as span:
        if _otel_available and span.is_recording():
            span.set_attribute("rpc.method", "run_shell")
            span.set_attribute("mcp.tool.argument.timeout_seconds", timeout_seconds)
            if _CAPTURE_CONTENT:
                span.set_attribute("process.command_line", command)
                span.set_attribute("process.working_directory", working_dir)
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=working_dir,
                timeout=timeout_seconds,
            )
            if _otel_available and span.is_recording():
                span.set_attribute("process.exit_code", result.returncode)
                if result.returncode != 0:
                    span.set_status(StatusCode.ERROR, f"exit code {result.returncode}")
            return json.dumps({
                "stdout": result.stdout[:_MAX_OUTPUT],
                "stderr": result.stderr[:_MAX_OUTPUT],
                "return_code": result.returncode,
            })
        except subprocess.TimeoutExpired:
            if _otel_available and span.is_recording():
                span.set_status(StatusCode.ERROR, f"timeout after {timeout_seconds}s")
            return json.dumps({"error": f"Command timed out after {timeout_seconds}s"})
        except Exception as exc:
            if _otel_available and span.is_recording():
                span.set_status(StatusCode.ERROR, str(exc))
            return json.dumps({"error": str(exc)})


if __name__ == "__main__":
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")

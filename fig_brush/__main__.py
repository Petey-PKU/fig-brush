"""Launch the local fig-brush MCP server over stdio."""

def main() -> int:
    from mcp_server.server import main as run_server
    return run_server()


if __name__ == "__main__":
    raise SystemExit(main())

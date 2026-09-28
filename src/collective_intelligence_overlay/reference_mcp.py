"""Loopback-only deterministic MCP tool server for integration examples."""

import argparse

from mcp.server import MCPServer

from .reference import csv_sum


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    server = MCPServer("reference-csv", log_level="WARNING")
    server.tool(name="csv_sum")(csv_sum)
    server.run(transport="streamable-http", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

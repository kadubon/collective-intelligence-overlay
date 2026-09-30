"""Test-only MCP resource using the official token-verifier interface."""

import argparse
import os
import secrets
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

from collective_intelligence_overlay.reference import csv_sum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--resource-url")
    parser.add_argument("--tool", choices=("csv_sum", "words"), default="csv_sum")
    args = parser.parse_args()
    endpoint = args.resource_url or f"http://127.0.0.1:{args.port}/mcp"
    expected = os.environ["CIO_TEST_MCP_TOKEN"]

    class Verifier:
        async def verify_token(self, token):
            if not secrets.compare_digest(token, expected):
                return None
            return AccessToken(
                token=token, client_id="test-client", scopes=["read"], resource=endpoint
            )

    server = MCPServer(
        "authenticated-csv",
        token_verifier=Verifier(),
        auth=AuthSettings(
            issuer_url="https://issuer.example.test/",
            resource_server_url=endpoint,
            required_scopes=["read"],
            validate_token_resource=True,
        ),
        log_level="WARNING",
    )
    if args.tool == "words":

        def words(text: str) -> dict[str, int]:
            # Test-only external call oracle; no input, credential or authority.
            if path := os.environ.get("CIO_TEST_MCP_CALL_AUDIT"):
                with Path(path).open("ab") as audit:
                    audit.write(b"call\n")
            return {"words": len(text.split())}

        server.tool(name="words")(words)
    else:
        server.tool(name="csv_sum")(csv_sum)
    server.run(transport="streamable-http", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

"""Test-only MCP resource using the official token-verifier interface."""

import argparse
import os
import secrets

from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

from collective_intelligence_overlay.reference import csv_sum


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    endpoint = f"http://127.0.0.1:{args.port}/mcp"
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
    server.tool(name="csv_sum")(csv_sum)
    server.run(transport="streamable-http", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

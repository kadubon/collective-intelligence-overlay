"""Owned official MCP fault fixture with an explicit private delay control file."""

import argparse
import asyncio
import os
import secrets
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--resource-url", required=True)
    parser.add_argument("--tool", choices=("words",), required=True)
    parser.add_argument("--delay-file", type=Path, required=True)
    args = parser.parse_args()
    expected = os.environ["CIO_TEST_MCP_TOKEN"]

    class Verifier:
        async def verify_token(self, token):
            if not secrets.compare_digest(token, expected):
                return None
            return AccessToken(
                token=token, client_id="test-client", scopes=["read"], resource=args.resource_url
            )

    server = MCPServer(
        "authenticated-csv",
        token_verifier=Verifier(),
        auth=AuthSettings(
            issuer_url="https://issuer.example.test/",
            resource_server_url=args.resource_url,
            required_scopes=["read"],
            validate_token_resource=True,
        ),
        log_level="WARNING",
    )

    def audit_call(path):
        with Path(path).open("ab") as audit:
            audit.write(b"call\n")

    async def words(text: str) -> dict[str, int]:
        delay = float(await asyncio.to_thread(args.delay_file.read_text))
        if not 0 <= delay <= 35:
            raise ValueError("finite private operator delay required")
        if path := os.environ.get("CIO_TEST_MCP_CALL_AUDIT"):
            await asyncio.to_thread(audit_call, path)
        await asyncio.sleep(delay)
        return {"words": len(text.split())}

    server.tool(name="words")(words)
    server.run(transport="streamable-http", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

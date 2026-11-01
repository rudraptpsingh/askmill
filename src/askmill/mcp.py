"""Optional MCP transport over the same profile/session API."""

import importlib.metadata
import json

from . import __version__
from .contract import Batch, Request, ResponseSchema
from .jsonio import MAX_BATCH_BYTES, json_size
from .profiles import load
from .runner import Session, run_batch as execute_batch


def create_server(config, store, lease):
    from mcp.server.fastmcp import FastMCP
    from jsonschema import Draft202012Validator

    class BoundedMCP(FastMCP):
        async def list_tools(self):
            listed = await super().list_tools()
            for tool in listed:
                # FastMCP argument models otherwise ignore unknown root keys.
                tool.inputSchema = {**tool.inputSchema, "additionalProperties": False}
                if tool.name == "run_request_v1":
                    tool.inputSchema["$id"] = "urn:askmill:mcp-run-request:v1"
            return listed

        async def call_tool(self, name, arguments):
            json_size(arguments, MAX_BATCH_BYTES)
            tools = {tool.name: tool for tool in await self.list_tools()}
            if name not in tools:
                raise ValueError("Unknown AskMill tool")
            error = next(
                Draft202012Validator(tools[name].inputSchema).iter_errors(arguments),
                None,
            )
            if error is not None:
                location = "/".join(str(part) for part in error.absolute_path)[:512]
                # Report the gate, never echo an entire source-bound request.
                raise ValueError(
                    f"Invalid MCP arguments ({error.validator}) at /{location}"
                )
            return await super().call_tool(name, arguments)

    sdk_version = importlib.metadata.version("mcp")
    server = BoundedMCP(
        "AskMill",
        instructions=(
            f"AskMill application {__version__}; MCP SDK {sdk_version}. "
            "Use run_request_v1 for complete source-bound Request v1/v2 metadata. "
            "Model output remains domain_acceptance=unverified."
        ),
    )
    # The SDK's FastMCP facade does not expose its low-level version parameter.
    # The qualified SDK exposes this public Server.version attribute underneath.
    server._mcp_server.version = __version__

    @server.resource("askmill://producer", mime_type="application/json")
    def producer_identity() -> str:
        """Application identity is distinct from protocol SDK identity."""
        return json.dumps(
            {
                "schema_version": "askmill.mcp-producer.v1",
                "application": "askmill",
                "application_version": __version__,
                "mcp_sdk_version": sdk_version,
                "full_request_tool": "run_request_v1",
                "full_request_tool_contract": "askmill.mcp-run-request.v1",
                "request_contracts": ["askmill.request.v1", "askmill.request.v2"],
                "domain_acceptance": "unverified",
            }
        )

    @server.tool()
    def run(
        profile: str,
        prompt: str,
        images: list[str] | None = None,
        max_tokens: int = 2048,
        timeout: float = 180.0,
        response_schema: dict | None = None,
    ) -> dict:
        """Run a bounded local text/vision call. Output is unverified."""
        request = Request(
            prompt=prompt,
            images=images or [],
            max_tokens=max_tokens,
            timeout=timeout,
            **(
                {
                    "schema_version": "askmill.request.v2",
                    "response_schema": ResponseSchema.model_validate(response_schema),
                }
                if response_schema is not None
                else {}
            ),
        )
        with Session(load(config, profile), store, lease) as session:
            return session.run(request).model_dump()

    @server.tool()
    def run_batch(
        profile: str, requests: list[dict], schema_version: str = "askmill.batch.v1"
    ) -> dict:
        """Run up to 16 bounded local tasks in one warm model session."""
        batch = Batch(
            schema_version=schema_version,
            requests=[Request.model_validate(item) for item in requests],
        )
        return execute_batch(load(config, profile), batch, store, lease)

    @server.tool()
    def run_request_v1(profile: str, request: Request) -> dict:
        """Execute a complete versioned Request, preserving all source metadata.

        Uses the same validation, profile, leases, receipts and result contract
        as CLI --request. Completion/schema validity never grant domain approval.
        """
        with Session(load(config, profile), store, lease) as session:
            return session.run(request).model_dump()

    return server


def serve(config, store, lease):
    create_server(config, store, lease).run(transport="stdio")

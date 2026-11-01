"""Optional MCP transport over the same profile/session API."""

from .contract import Batch, Request
from .profiles import load
from .runner import Session, run_batch as execute_batch


def create_server(config, store, lease):
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("AskMill")

    @server.tool()
    def run(
        profile: str,
        prompt: str,
        images: list[str] | None = None,
        max_tokens: int = 2048,
        timeout: float = 180.0,
    ) -> dict:
        """Run a bounded local text/vision call. Output is unverified."""
        request = Request(
            prompt=prompt, images=images or [], max_tokens=max_tokens, timeout=timeout
        )
        with Session(load(config, profile), store, lease) as session:
            return session.run(request).model_dump()

    @server.tool()
    def run_batch(profile: str, requests: list[dict]) -> dict:
        """Run up to 16 bounded local tasks in one warm model session."""
        batch = Batch(requests=[Request.model_validate(item) for item in requests])
        return execute_batch(load(config, profile), batch, store, lease)

    return server


def serve(config, store, lease):
    create_server(config, store, lease).run(transport="stdio")

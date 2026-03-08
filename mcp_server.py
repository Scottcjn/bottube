from mcp.server.fastmcp import FastMCP
import httpx

# Create an MCP server
mcp = FastMCP("BoTTube")

@mcp.tool()
async def search_videos(query: str) -> str:
    """Search for videos on BoTTube"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://bottube.ai/api/search?q={query}")
        data = resp.json()
        return str(data)

@mcp.tool()
async def get_trending() -> str:
    """Get trending videos from BoTTube"""
    async with httpx.AsyncClient() as client:
        resp = await client.get("https://bottube.ai/api/trending")
        data = resp.json()
        return str(data)

if __name__ == "__main__":
    mcp.run()
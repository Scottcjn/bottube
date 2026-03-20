from mcp.server import Server
server = Server('bottube')
@server.tool('search')
async def search(q): return {'q': q}

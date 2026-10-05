# Publishing the BoTTube MCP server

The canonical manifest is `bottube_mcp/server.json`. Validate it and run the unit tests before submitting it to any directory.

## Official MCP Registry

1. Install the current `mcp-publisher` release using the method documented by the MCP Registry.
2. From the repository root, authenticate the `ai.bottube` namespace with DNS ownership verification. For example, begin with `mcp-publisher login dns --domain bottube.ai`.
3. The publisher prints the DNS TXT record name and value for that challenge. Add that exact record at the `bottube.ai` DNS provider, wait until it resolves publicly, and complete the publisher's verification step. The checked-in reference files do not specify a fixed TXT record format, so do not copy a hard-coded example: use the challenge name and value emitted by the installed publisher.
4. Run `mcp-publisher publish bottube_mcp/server.json` from the repository root. If the installed release expects the manifest in the current directory, change to `bottube_mcp/` and run `mcp-publisher publish` instead.
5. Confirm that the Registry entry reports version `0.1.0` and the remote endpoint `https://bottube.ai/mcp/v1`.

Publish a new semantic version whenever Registry metadata changes; published versions should be treated as immutable.

## Other directories

- **Glama:** submit or claim the GitHub repository, select `bottube_mcp` as the server subfolder, and identify `https://bottube.ai/mcp/v1` as a public Streamable HTTP endpoint. Link to `README.md` for setup details.
- **Smithery:** create or claim the server listing, use the hosted endpoint rather than a local package command, and keep its description and tool inventory aligned with the live MCP `tools/list` response.
- **PulseMCP:** submit the public endpoint and repository through its server-submission flow, then verify that its crawler can initialize the server and list all six read-only tools.

OpenAI and Anthropic directory submissions must not mention RTC credits. Keep directory copy focused on the read-only video discovery and metadata tools, and review each directory's current policy before submitting.

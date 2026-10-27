"""FinLit MCP server: read-only Indian stock data for AI assistants (Model Context Protocol, Streamable HTTP, stateless).

Every tool answers by calling the site's own public routes in-process as an anonymous visitor, so plan limits, validation, caching and
numbers are the website's. See protocol.py (JSON-RPC), tools.py (the tools), server.py (the /mcp route and its safeguards).
"""

# MCP Servers Integration

SDK에서 MCP (Model Context Protocol) 서버를 통합하는 방법.

## Supported Server Types

| Type | Config | Use Case |
|------|--------|----------|
| `stdio` | `{ command, args?, env? }` | Local CLI tools |
| `sse` | `{ type: 'sse', url, headers? }` | Server-Sent Events |
| `http` | `{ type: 'http', url, headers? }` | HTTP Streamable |
| `sdk` | `{ type: 'sdk', name }` + instance | In-process servers |

## Basic Usage

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

const response = query({
  prompt: "Use the MCP tool to search documentation",
  options: {
    mcpServers: {
      "context7": {
        command: "npx",
        args: ["-y", "@anthropic-ai/context7-mcp"]
      }
    }
  }
});
```

## Multiple Servers

```typescript
options: {
  mcpServers: {
    "docs": {
      command: "npx",
      args: ["-y", "@anthropic-ai/context7-mcp"]
    },
    "database": {
      type: "http",
      url: "http://localhost:3001/mcp",
      headers: { "Authorization": "Bearer token" }
    }
  }
}
```

## Dynamic Server Management

```typescript
const response = query({ prompt: "..." });

// Add servers dynamically
const result = await response.setMcpServers({
  "new-server": { command: "node", args: ["./server.js"] }
});

console.log("Added:", result.added);
console.log("Removed:", result.removed);
console.log("Errors:", result.errors);

// Check server status
const status = await response.mcpServerStatus();
// Returns: [{ name, status: 'connected'|'failed'|'needs-auth'|'pending', serverInfo? }]
```

## In-Process SDK Server

```typescript
import { query, createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";

const myServer = createSdkMcpServer({
  name: "my-tools",
  version: "1.0.0",
  tools: [
    tool("greet", "Say hello", { name: z.string() }, async ({ name }) => ({
      content: [{ type: "text", text: `Hello, ${name}!` }]
    }))
  ]
});

const response = query({
  prompt: "Use the greet tool",
  options: {
    mcpServers: { "my-tools": myServer }
  }
});
```

## Init Message MCP Status

```typescript
for await (const msg of response) {
  if (msg.type === "system" && msg.subtype === "init") {
    console.log("MCP Servers:", msg.mcp_servers);
    // [{ name: "context7", status: "connected" }]
  }
}
```

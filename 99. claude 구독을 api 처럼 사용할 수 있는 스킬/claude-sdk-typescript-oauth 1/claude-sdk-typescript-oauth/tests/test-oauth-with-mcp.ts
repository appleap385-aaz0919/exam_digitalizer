/**
 * OAuth + MCP 서버 통합 테스트
 * MCP 서버를 OAuth 인증과 함께 사용
 */
import { query } from "@anthropic-ai/claude-agent-sdk";

if (process.env.ANTHROPIC_API_KEY) {
  throw new Error("ANTHROPIC_API_KEY 설정됨. 해제 필요: unset ANTHROPIC_API_KEY");
}

async function testOAuthWithMcp() {
  console.log("[TEST] OAuth + MCP 서버 테스트 시작...");

  const response = query({
    prompt:
      "Use the context7 MCP to find documentation about 'query function' in the @anthropic-ai/claude-code library. Reply with a brief summary.",
    options: {
      maxTurns: 5,
      permissionMode: "dontAsk",
      persistSession: false,
      mcpServers: {
        context7: {
          command: "npx",
          args: ["-y", "@anthropic-ai/context7-mcp"],
        },
      },
    },
  });

  for await (const msg of response) {
    if (msg.type === "system" && msg.subtype === "init") {
      console.log("[TEST] Session ID:", msg.session_id);
      if ("mcp_servers" in msg) {
        console.log("[TEST] MCP Servers:", (msg as any).mcp_servers);
      }
    }
    if (msg.type === "result") {
      if (msg.subtype === "success") {
        console.log("[TEST] PASSED - Result:", msg.result);
        console.log("[TEST] Cost: $" + (msg.total_cost_usd?.toFixed(4) ?? "N/A"));
        return true;
      }
      console.error("[TEST] Error subtype:", msg.subtype);
      throw new Error(`Failed: ${msg.subtype}`);
    }
  }
  return false;
}

testOAuthWithMcp()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error("[TEST] FAILED:", e.message);
    process.exit(1);
  });

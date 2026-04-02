/**
 * 기본 OAuth 인증 테스트 (레거시 호환)
 * API 키 없이 OAuth 토큰으로 인증 확인
 */
import { query } from "@anthropic-ai/claude-agent-sdk";

if (process.env.ANTHROPIC_API_KEY) {
  throw new Error("ANTHROPIC_API_KEY 설정됨. 해제 필요: unset ANTHROPIC_API_KEY");
}

async function testOAuthAuth() {
  console.log("[TEST] OAuth 인증 테스트 시작...");

  const response = query({
    prompt: "Reply with exactly: 'OAuth OK'",
    options: {
      maxTurns: 1,
      allowedTools: [],
      permissionMode: "dontAsk",
      persistSession: false,
    },
  });

  for await (const msg of response) {
    if (msg.type === "system" && msg.subtype === "init") {
      console.log("[TEST] Session ID:", msg.session_id);
    }
    if (msg.type === "result") {
      if (msg.subtype === "success") {
        console.log("[TEST] PASSED - Result:", msg.result);
        console.log("[TEST] Cost: $" + (msg.total_cost_usd?.toFixed(4) ?? "N/A"));
        return true;
      }
      throw new Error(`Failed: ${msg.subtype}`);
    }
  }
  return false;
}

testOAuthAuth()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error("[TEST] FAILED:", e.message);
    process.exit(1);
  });

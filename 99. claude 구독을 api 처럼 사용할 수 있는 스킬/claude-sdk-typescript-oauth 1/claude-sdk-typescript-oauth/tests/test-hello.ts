/**
 * 간단한 OAuth 인증 hello 테스트
 * API 키 없이 Claude Code OAuth 토큰으로 동작 확인
 */
import { query } from "@anthropic-ai/claude-agent-sdk";

if (process.env.ANTHROPIC_API_KEY) {
  console.error("[ERROR] ANTHROPIC_API_KEY가 설정되어 있습니다. OAuth 테스트를 위해 해제하세요:");
  console.error("  unset ANTHROPIC_API_KEY");
  process.exit(1);
}

async function testHello() {
  console.log("[TEST] OAuth Hello 테스트 시작...");
  console.log("[TEST] API 키 없이 OAuth 인증 사용 중");

  const response = query({
    prompt: "Say exactly: 'Hello from OAuth!' and nothing else.",
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
        console.log("[TEST] PASSED");
        console.log("[TEST] Result:", msg.result);
        console.log("[TEST] Cost: $" + (msg.total_cost_usd?.toFixed(4) ?? "N/A"));
        return true;
      }
      throw new Error(`실패: ${msg.subtype}`);
    }
  }
  return false;
}

testHello()
  .then(() => {
    console.log("[TEST] OAuth 인증 정상 동작 확인");
    process.exit(0);
  })
  .catch((e) => {
    console.error("[TEST] FAILED:", e.message);
    process.exit(1);
  });

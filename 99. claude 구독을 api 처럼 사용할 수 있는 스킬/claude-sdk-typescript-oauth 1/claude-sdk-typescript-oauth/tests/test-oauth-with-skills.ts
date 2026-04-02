/**
 * OAuth + Skills 통합 테스트
 * settingSources로 스킬 로드 및 확인
 */
import { query } from "@anthropic-ai/claude-agent-sdk";

if (process.env.ANTHROPIC_API_KEY) {
  throw new Error("ANTHROPIC_API_KEY 설정됨. 해제 필요: unset ANTHROPIC_API_KEY");
}

async function testOAuthWithSkills() {
  console.log("[TEST] OAuth + Skills 테스트 시작...");

  const response = query({
    prompt: "List all available skills and slash commands. Reply with the count of each.",
    options: {
      maxTurns: 1,
      allowedTools: [],
      permissionMode: "dontAsk",
      persistSession: false,
      settingSources: ["user", "project"],
    },
  });

  for await (const msg of response) {
    if (msg.type === "system" && msg.subtype === "init") {
      console.log("[TEST] Session ID:", msg.session_id);
      if ("skills" in msg) {
        console.log("[TEST] Available Skills:", (msg as any).skills);
        console.log("[TEST] Skills count:", (msg as any).skills?.length || 0);
      }
      if ("slash_commands" in msg) {
        console.log("[TEST] Slash Commands:", (msg as any).slash_commands);
        console.log("[TEST] Commands count:", (msg as any).slash_commands?.length || 0);
      }
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

testOAuthWithSkills()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error("[TEST] FAILED:", e.message);
    process.exit(1);
  });

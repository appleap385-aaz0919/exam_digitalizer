/**
 * Adaptive Thinking 테스트
 * SDK 0.2.x의 thinking 옵션과 effort 레벨 테스트
 */
import { query } from "@anthropic-ai/claude-agent-sdk";

if (process.env.ANTHROPIC_API_KEY) {
  throw new Error("ANTHROPIC_API_KEY 설정됨. 해제 필요: unset ANTHROPIC_API_KEY");
}

async function testAdaptiveThinking() {
  console.log("[TEST] Adaptive Thinking 테스트 시작...");
  console.log("[TEST] thinking: { type: 'adaptive' }, effort: 'low'");

  const response = query({
    prompt: "What is 2 + 2? Reply with just the number.",
    options: {
      maxTurns: 1,
      allowedTools: [],
      permissionMode: "dontAsk",
      persistSession: false,
      thinking: { type: "adaptive" },
      effort: "low",
    },
  });

  let hasThinking = false;

  for await (const msg of response) {
    if (msg.type === "system" && msg.subtype === "init") {
      console.log("[TEST] Session ID:", msg.session_id);
    }
    if (msg.type === "assistant" && "message" in msg) {
      const content = (msg as any).message?.content;
      if (Array.isArray(content)) {
        for (const block of content) {
          if (block.type === "thinking") {
            hasThinking = true;
            console.log("[TEST] Thinking detected (length:", block.thinking?.length ?? 0, "chars)");
          }
        }
      }
    }
    if (msg.type === "result") {
      if (msg.subtype === "success") {
        console.log("[TEST] PASSED");
        console.log("[TEST] Result:", msg.result);
        console.log("[TEST] Had thinking:", hasThinking);
        console.log("[TEST] Cost: $" + (msg.total_cost_usd?.toFixed(4) ?? "N/A"));
        return true;
      }
      throw new Error(`실패: ${msg.subtype}`);
    }
  }
  return false;
}

async function testHighEffort() {
  console.log("\n[TEST] High Effort 테스트 시작...");
  console.log("[TEST] thinking: { type: 'adaptive' }, effort: 'high'");

  const response = query({
    prompt: "Explain in one sentence why the sky is blue.",
    options: {
      maxTurns: 1,
      allowedTools: [],
      permissionMode: "dontAsk",
      persistSession: false,
      thinking: { type: "adaptive" },
      effort: "high",
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

(async () => {
  await testAdaptiveThinking();
  await testHighEffort();
  console.log("\n[TEST] Thinking 테스트 모두 통과");
  process.exit(0);
})().catch((e) => {
  console.error("[TEST] FAILED:", e.message);
  process.exit(1);
});

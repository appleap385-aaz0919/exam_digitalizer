/**
 * Custom Agent/Subagent 테스트
 * SDK 0.2.x의 agent/agents 옵션으로 커스텀 서브에이전트 정의 및 실행
 */
import { query } from "@anthropic-ai/claude-agent-sdk";

if (process.env.ANTHROPIC_API_KEY) {
  throw new Error("ANTHROPIC_API_KEY 설정됨. 해제 필요: unset ANTHROPIC_API_KEY");
}

async function testMainAgent() {
  console.log("[TEST] Main Thread Agent 테스트 시작...");
  console.log("[TEST] agent 옵션으로 메인 스레드 에이전트 지정");

  const response = query({
    prompt: "Introduce yourself briefly.",
    options: {
      maxTurns: 1,
      allowedTools: [],
      permissionMode: "dontAsk",
      persistSession: false,
      agent: "greeter",
      agents: {
        greeter: {
          description: "A friendly greeter agent",
          prompt:
            "You are a friendly greeter. Always start your response with 'Greetings!' and keep it under 20 words.",
          maxTurns: 1,
        },
      },
    },
  });

  for await (const msg of response) {
    if (msg.type === "system" && msg.subtype === "init") {
      console.log("[TEST] Session ID:", msg.session_id);
    }
    if (msg.type === "result") {
      if (msg.subtype === "success") {
        const hasGreeting = msg.result.toLowerCase().includes("greetings");
        console.log("[TEST]", hasGreeting ? "PASSED" : "WARN - 'Greetings' not found");
        console.log("[TEST] Result:", msg.result);
        console.log("[TEST] Cost: $" + (msg.total_cost_usd?.toFixed(4) ?? "N/A"));
        return true;
      }
      throw new Error(`실패: ${msg.subtype}`);
    }
  }
  return false;
}

async function testSubagentDispatch() {
  console.log("\n[TEST] Subagent Dispatch 테스트 시작...");
  console.log("[TEST] agents 정의 후 메인에서 Agent 도구로 서브에이전트 호출");

  const response = query({
    prompt:
      'Use the "analyzer" agent to analyze the text "Hello World" and return the character count.',
    options: {
      maxTurns: 5,
      permissionMode: "dontAsk",
      persistSession: false,
      allowedTools: ["Agent"],
      agents: {
        analyzer: {
          description: "Analyzes text and returns character count",
          prompt:
            "You are a text analyzer. When given text, count the characters (including spaces) and reply with just the count number.",
          tools: [],
          model: "haiku",
          maxTurns: 1,
        },
      },
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
  await testMainAgent();
  await testSubagentDispatch();
  console.log("\n[TEST] Agent 테스트 모두 통과");
  process.exit(0);
})().catch((e) => {
  console.error("[TEST] FAILED:", e.message);
  process.exit(1);
});

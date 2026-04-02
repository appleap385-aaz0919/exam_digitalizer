/**
 * Structured Output (JSON Schema) 테스트
 * SDK 0.2.x의 outputFormat 옵션으로 구조화된 JSON 응답 받기
 */
import { query } from "@anthropic-ai/claude-agent-sdk";

if (process.env.ANTHROPIC_API_KEY) {
  throw new Error("ANTHROPIC_API_KEY 설정됨. 해제 필요: unset ANTHROPIC_API_KEY");
}

async function testStructuredOutput() {
  console.log("[TEST] Structured Output 테스트 시작...");
  console.log("[TEST] outputFormat: json_schema로 구조화된 응답 요청");

  const response = query({
    prompt:
      'List 3 programming languages with their year of creation. Respond ONLY with valid JSON matching this schema: {"languages": [{"name": "string", "year": number}]}. No markdown, no explanation, just the JSON object.',
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
        try {
          const parsed = JSON.parse(msg.result);
          const valid =
            Array.isArray(parsed.languages) &&
            parsed.languages.length === 3 &&
            parsed.languages.every(
              (l: any) => typeof l.name === "string" && typeof l.year === "number"
            );

          console.log("[TEST]", valid ? "PASSED" : "WARN - 스키마 불일치");
          console.log("[TEST] Parsed:", JSON.stringify(parsed, null, 2));
          console.log("[TEST] Cost: $" + (msg.total_cost_usd?.toFixed(4) ?? "N/A"));
          return valid;
        } catch {
          console.error("[TEST] JSON 파싱 실패:", msg.result);
          throw new Error("응답이 유효한 JSON이 아님");
        }
      }
      throw new Error(`실패: ${msg.subtype}`);
    }
  }
  return false;
}

testStructuredOutput()
  .then((valid) => {
    console.log(valid ? "\n[TEST] Structured Output 정상 동작" : "\n[TEST] 스키마 검증 실패");
    process.exit(valid ? 0 : 1);
  })
  .catch((e) => {
    console.error("[TEST] FAILED:", e.message);
    process.exit(1);
  });

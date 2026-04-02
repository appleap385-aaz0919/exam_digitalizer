/**
 * LLM Proxy Server
 *
 * Claude 구독(OAuth)을 API처럼 사용하기 위한 Node.js 프록시.
 * Python 백엔드가 HTTP POST로 호출하면, Claude Agent SDK를 통해
 * OAuth 인증된 Claude API를 호출하고 결과를 반환합니다.
 *
 * 사용:
 *   cd llm-proxy && npm install && npm start
 *
 * 엔드포인트:
 *   POST /api/query  — LLM 호출
 *   GET  /health     — 헬스체크
 */

import express from "express";
import { query } from "@anthropic-ai/claude-agent-sdk";

const app = express();
app.use(express.json({ limit: "10mb" }));

const PORT = process.env.LLM_PROXY_PORT || 3100;

// 헬스체크
app.get("/health", (req, res) => {
  res.json({ status: "ok", mode: "claude-oauth-proxy" });
});

// LLM 호출
app.post("/api/query", async (req, res) => {
  const {
    system_prompt = "",
    user_prompt = "",
    agent = "unknown",
    ref_id = "",
    model = "sonnet",
    max_tokens = 4096,
    temperature = 0.0,
  } = req.body;

  if (!user_prompt) {
    return res.status(400).json({ error: "user_prompt is required" });
  }

  const startTime = Date.now();

  try {
    // 시스템 프롬프트 + 유저 프롬프트 결합
    const fullPrompt = system_prompt
      ? `<system>${system_prompt}</system>\n\n${user_prompt}`
      : user_prompt;

    const response = query({
      prompt: fullPrompt,
      options: {
        maxTurns: 1,
        model,
        allowedTools: [],
        permissionMode: "dontAsk",
        persistSession: false,
      },
    });

    let resultText = "";
    let costUsd = 0;
    let sessionId = "";

    for await (const msg of response) {
      if (msg.type === "system" && msg.subtype === "init") {
        sessionId = msg.session_id || "";
      }
      if (msg.type === "assistant" && "message" in msg) {
        const content = msg.message?.content || [];
        for (const block of content) {
          if (block.type === "text") {
            resultText += block.text;
          }
        }
      }
      if (msg.type === "result" && msg.subtype === "success") {
        resultText = msg.result || resultText;
        costUsd = msg.total_cost_usd || 0;
      }
      if (msg.type === "result" && msg.subtype === "error") {
        throw new Error(msg.error || "Claude SDK error");
      }
    }

    const durationMs = Date.now() - startTime;

    res.json({
      content: resultText,
      model,
      cost_usd: costUsd,
      duration_ms: durationMs,
      session_id: sessionId,
      agent,
      ref_id,
    });

    console.log(
      `[${new Date().toISOString()}] ${agent}/${ref_id} | ${model} | ${durationMs}ms | $${costUsd.toFixed(4)}`
    );
  } catch (error) {
    const durationMs = Date.now() - startTime;
    console.error(
      `[${new Date().toISOString()}] ERROR ${agent}/${ref_id} | ${error.message}`
    );
    res.status(500).json({
      error: error.message,
      agent,
      ref_id,
      duration_ms: durationMs,
    });
  }
});

app.listen(PORT, () => {
  console.log(`LLM Proxy running on http://localhost:${PORT}`);
  console.log("Using Claude OAuth (subscription-based, no API key needed)");
});

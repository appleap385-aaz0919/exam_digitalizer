---
name: claude-sdk-typescript-oauth
description: Use when integrating the Claude Agent SDK in TypeScript with OAuth authentication via Claude Code instead of setting ANTHROPIC_API_KEY. Covers thinking, agents, structured output, MCP, and permissions.
---

# claude-sdk-typescript-oauth

Claude Agent SDK 0.2.x를 OAuth 인증으로 사용하는 TypeScript 레퍼런스 (API 키 불필요).

## Prerequisites

1. **Claude Code CLI 설치**
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

2. **OAuth 인증 완료**
   ```bash
   claude  # 최초 실행 시 브라우저에서 OAuth 인증
   ```

3. **API 키 미설정 확인**
   ```bash
   unset ANTHROPIC_API_KEY
   ```

## Quick Start

```bash
npm install
npm test              # hello 테스트
npm run test:thinking # adaptive thinking 테스트
npm run test:agents   # custom agent 테스트
npm run test:all      # 전체 테스트
```

## Core API

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

const response = query({
  prompt: "Hello!",
  options: {
    maxTurns: 1,
    allowedTools: [],
    permissionMode: "dontAsk",
    persistSession: false,
  },
});

for await (const msg of response) {
  if (msg.type === "system" && msg.subtype === "init") {
    console.log("Session:", msg.session_id);
  }
  if (msg.type === "result" && msg.subtype === "success") {
    console.log("Result:", msg.result);
    console.log("Cost:", msg.total_cost_usd);
  }
}
```

## Key Features (SDK 0.2.x)

### 1. Adaptive Thinking

Claude가 자율적으로 사고 깊이를 결정. effort 레벨로 조절 가능.

```typescript
options: {
  thinking: { type: "adaptive" },  // Opus 4.6+ 기본값
  effort: "high",                   // low | medium | high | max
}
```

See [references/THINKING.md](references/THINKING.md)

### 2. Custom Agents

서브에이전트를 정의하고 Agent 도구로 디스패치.

```typescript
options: {
  agent: "reviewer",  // 메인 스레드 에이전트
  agents: {
    reviewer: {
      description: "코드 리뷰 전문가",
      prompt: "You are a code reviewer...",
      tools: ["Read", "Grep", "Glob"],
      model: "haiku",
      maxTurns: 3,
    },
  },
}
```

See [references/AGENTS.md](references/AGENTS.md)

### 3. Structured Output

JSON Schema로 구조화된 응답.

```typescript
options: {
  outputFormat: {
    type: "json_schema",
    schema: {
      type: "object",
      properties: {
        result: { type: "string" },
        confidence: { type: "number" },
      },
      required: ["result", "confidence"],
    },
  },
}
```

### 4. MCP Servers

See [references/MCP-SERVERS.md](references/MCP-SERVERS.md)

### 5. Permissions Control

See [references/PERMISSIONS.md](references/PERMISSIONS.md)

### 6. Skills Integration

See [references/SKILLS.md](references/SKILLS.md)

## New Options Summary (0.2.x)

| Option | Type | Description |
|--------|------|-------------|
| `thinking` | `ThinkingConfig` | Adaptive/enabled/disabled thinking |
| `effort` | `EffortLevel` | low/medium/high/max |
| `agent` | `string` | 메인 스레드 에이전트 이름 |
| `agents` | `Record<string, AgentDefinition>` | 커스텀 서브에이전트 정의 |
| `outputFormat` | `OutputFormat` | JSON Schema 구조화 출력 |
| `tools` | `string[] \| preset` | 사용 가능 도구 제한 |
| `maxBudgetUsd` | `number` | 비용 상한 (USD) |
| `model` | `string` | 모델 선택 (claude-sonnet-4-6 등) |
| `sandbox` | `SandboxConfig` | 명령 실행 샌드박스 |
| `plugins` | `SdkPluginConfig[]` | 로컬 플러그인 로드 |
| `persistSession` | `boolean` | 세션 디스크 저장 여부 |
| `betas` | `SdkBeta[]` | 베타 기능 (1M context 등) |
| `hooks` | `HookCallbackMatcher[]` | 이벤트 훅 콜백 |
| `promptSuggestions` | `boolean` | 다음 프롬프트 제안 |
| `agentProgressSummaries` | `boolean` | 서브에이전트 진행 요약 |

## Authentication Flow

```
Client Request
     |
     v
Node.js Server
     |
     v
Claude Agent SDK (query())
     |
     v
Claude Code CLI Process (spawned)
     |
     v
OAuth Token (Claude Code login)
     |
     v
Anthropic API
```

## Server Integration

```typescript
import express from "express";
import { query } from "@anthropic-ai/claude-agent-sdk";

const app = express();
app.use(express.json());

app.post("/api/chat", async (req, res) => {
  const { prompt } = req.body;

  const response = query({
    prompt,
    options: {
      maxTurns: 3,
      allowedTools: [],
      permissionMode: "dontAsk",
      maxBudgetUsd: 0.10,
    },
  });

  let result = "";
  for await (const msg of response) {
    if (msg.type === "result" && msg.subtype === "success") {
      result = msg.result;
    }
  }

  res.json({ success: true, result });
});

app.listen(3000);
```

## Session Management (0.2.x)

```typescript
import {
  listSessions,
  getSessionInfo,
  getSessionMessages,
  forkSession,
  renameSession,
} from "@anthropic-ai/claude-agent-sdk";

// 세션 목록 조회
const sessions = await listSessions({ dir: "." });

// 세션 정보
const info = await getSessionInfo(sessionId);

// 세션 메시지 읽기
const messages = await getSessionMessages(sessionId, { limit: 10 });

// 세션 분기 (fork)
const { sessionId: newId } = await forkSession(sessionId);

// 세션 이름 변경
await renameSession(sessionId, "My Session");
```

## Limitations

- **서버 사이드 전용**: Node.js 환경에서만 작동 (CLI 프로세스 필요)
- **브라우저 불가**: 클라이언트에서 직접 호출 불가
- **개발/개인용 권장**: 프로덕션 배포 시 API 키 사용 권장

## Troubleshooting

### "ANTHROPIC_API_KEY 설정됨" 오류
```bash
unset ANTHROPIC_API_KEY
```

### OAuth 인증 만료
```bash
claude  # 재인증
```

### CLI를 찾을 수 없음
```bash
npm install -g @anthropic-ai/claude-code
```

### zod 관련 오류
SDK 0.2.x는 zod를 peer dependency로 사용. 직접 설치 불필요 (SDK가 내장).

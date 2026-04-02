# Custom Agents

SDK 0.2.x에서 커스텀 에이전트/서브에이전트를 정의하고 사용하는 방법.

## Agent vs Agents

| Option | Role | Description |
|--------|------|-------------|
| `agent` | 메인 스레드 에이전트 | 메인 대화에 적용될 에이전트 이름 |
| `agents` | 에이전트 정의 | 사용 가능한 서브에이전트 맵 |

## AgentDefinition

```typescript
type AgentDefinition = {
  description: string;        // 에이전트 설명 (Agent 도구가 선택 시 참조)
  prompt: string;             // 시스템 프롬프트
  tools?: string[];           // 허용 도구 (생략 시 부모 상속)
  disallowedTools?: string[]; // 차단 도구
  model?: string;             // 모델 ('haiku', 'sonnet', 'opus' 또는 전체 ID)
  maxTurns?: number;          // 최대 턴 수
  skills?: string[];          // 프리로드 스킬
  initialPrompt?: string;     // 초기 프롬프트 (메인 에이전트용)
  mcpServers?: AgentMcpServerSpec[]; // MCP 서버
};
```

## Main Thread Agent

메인 대화에 에이전트 시스템 프롬프트와 도구 제한 적용:

```typescript
const response = query({
  prompt: "Review this code for bugs",
  options: {
    agent: "code-reviewer",
    agents: {
      "code-reviewer": {
        description: "코드 품질 및 버그 검출 전문가",
        prompt: "You are a senior code reviewer. Focus on bugs, security issues, and performance.",
        tools: ["Read", "Grep", "Glob"],
        model: "sonnet",
      },
    },
  },
});
```

## Subagent Dispatch

메인에서 Agent 도구를 통해 서브에이전트 호출:

```typescript
const response = query({
  prompt: "Analyze the codebase security and test coverage in parallel.",
  options: {
    maxTurns: 10,
    allowedTools: ["Agent", "Read", "Grep", "Glob"],
    agents: {
      "security-scanner": {
        description: "보안 취약점 스캔 전문가",
        prompt: "Scan for security vulnerabilities...",
        tools: ["Read", "Grep", "Glob"],
        model: "haiku",
        maxTurns: 5,
      },
      "test-analyzer": {
        description: "테스트 커버리지 분석가",
        prompt: "Analyze test coverage and gaps...",
        tools: ["Read", "Grep", "Glob", "Bash"],
        model: "haiku",
        maxTurns: 5,
      },
    },
  },
});
```

## Query Methods

```typescript
const response = query({ prompt: "..." });

// 사용 가능한 서브에이전트 조회
const agents = await response.supportedAgents();
// Returns: AgentInfo[] = [{ name, description, model? }]

// 계정 정보 조회
const account = await response.accountInfo();
// Returns: AccountInfo = { email, organization, apiProvider, ... }
```

## Agent Progress Summaries

서브에이전트 진행 상황을 주기적으로 AI 요약으로 받기:

```typescript
options: {
  agentProgressSummaries: true,  // ~30초마다 요약 생성
  agents: { ... },
}

for await (const msg of response) {
  if (msg.type === "task_progress") {
    console.log("Progress:", msg.summary);
  }
}
```

## Model Routing

에이전트별로 다른 모델 지정하여 비용 최적화:

```typescript
agents: {
  "heavy-analyzer": {
    description: "Deep analysis",
    prompt: "...",
    model: "opus",      // 복잡한 분석
  },
  "light-worker": {
    description: "Simple tasks",
    prompt: "...",
    model: "haiku",     // 간단한 작업 (3x 비용 절감)
  },
}
```

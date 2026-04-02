# Thinking & Effort Control

SDK 0.2.x에서 Claude의 사고/추론 동작을 제어하는 방법.

## Thinking Config

| Type | Description | Models |
|------|-------------|--------|
| `{ type: 'adaptive' }` | Claude가 자율적으로 사고 깊이 결정 | Opus 4.6+ (기본값) |
| `{ type: 'enabled', budgetTokens: N }` | 고정 사고 토큰 예산 | 구형 모델 |
| `{ type: 'disabled' }` | 사고 비활성화 | 전체 |

## Effort Levels

| Level | Description | Use Case |
|-------|-------------|----------|
| `'low'` | 최소 사고, 가장 빠른 응답 | 단순 질문, 분류 |
| `'medium'` | 적당한 사고 | 일반 대화, 간단한 코드 |
| `'high'` | 깊은 추론 (기본값) | 복잡한 분석, 코드 리뷰 |
| `'max'` | 최대 노력 | 아키텍처 설계, 디버깅 (Opus 4.6) |

## Usage

### Adaptive Thinking (권장)

```typescript
const response = query({
  prompt: "Analyze this architecture...",
  options: {
    thinking: { type: "adaptive" },
    effort: "high",
  },
});
```

### Fixed Budget

```typescript
options: {
  thinking: { type: "enabled", budgetTokens: 10000 },
}
```

### Disabled

```typescript
options: {
  thinking: { type: "disabled" },
}
```

## Thinking in Messages

thinking 블록은 assistant 메시지의 content 배열에 포함:

```typescript
for await (const msg of response) {
  if (msg.type === "assistant" && "message" in msg) {
    const content = msg.message?.content;
    if (Array.isArray(content)) {
      for (const block of content) {
        if (block.type === "thinking") {
          console.log("Thinking:", block.thinking);
        }
        if (block.type === "text") {
          console.log("Response:", block.text);
        }
      }
    }
  }
}
```

## Deprecated

`maxThinkingTokens` 옵션은 deprecated. `thinking` 옵션 사용 권장.

```typescript
// DEPRECATED
options: { maxThinkingTokens: 10000 }

// RECOMMENDED
options: { thinking: { type: "adaptive" } }
```

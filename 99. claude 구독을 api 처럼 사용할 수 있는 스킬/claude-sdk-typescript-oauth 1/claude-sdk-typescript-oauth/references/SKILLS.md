# Skills Integration

SDK에서 Claude Code Skills를 로드하고 사용하는 방법.

## Loading Skills

`settingSources` 옵션으로 파일시스템 설정에서 스킬을 로드:

```typescript
import { query } from "@anthropic-ai/claude-agent-sdk";

const response = query({
  prompt: "Use /commit to create a git commit",
  options: {
    settingSources: ["user", "project"], // 스킬 설정 로드
  }
});
```

## Setting Sources

| Source | Path | Description |
|--------|------|-------------|
| `user` | `~/.claude/settings.json` | Global user settings |
| `project` | `.claude/settings.json` | Project settings |
| `local` | `.claude/settings.local.json` | Local settings (gitignored) |

## Checking Available Skills

```typescript
for await (const msg of response) {
  if (msg.type === "system" && msg.subtype === "init") {
    console.log("Skills:", msg.skills);
    console.log("Slash Commands:", msg.slash_commands);
  }
}
```

## Using supportedCommands()

```typescript
const response = query({ prompt: "..." });

const commands = await response.supportedCommands();
// Returns: [{ name, description, argumentHint }]

for (const cmd of commands) {
  console.log(`/${cmd.name} - ${cmd.description}`);
}
```

## Plugin-Based Skills

```typescript
const response = query({
  prompt: "...",
  options: {
    plugins: [
      { type: "local", path: "./my-plugin" }
    ]
  }
});
```

Plugin structure:
```
my-plugin/
├── plugin.json
└── skills/
    └── my-skill/
        └── SKILL.md
```

## Invoking Skills via Prompt

```typescript
const response = query({
  prompt: "/commit -m 'feat: add new feature'",
  options: {
    settingSources: ["user", "project"],
  }
});
```

## Example Output

```
Skills: [
  'agent-browser',
  'frontend-design',
  'skill-creator',
  ...
]
Slash Commands: [
  'agent-browser',
  'commit',
  'review',
  ...
]
```

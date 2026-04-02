# Permissions Control

SDK에서 도구 실행 및 디렉토리 접근 권한을 제어하는 방법.

## Tool Allow/Deny

```typescript
options: {
  // 자동 허용 (프롬프트 없이 실행)
  allowedTools: ["Read", "Glob", "Grep"],

  // 완전 비활성화 (컨텍스트에서 제거)
  disallowedTools: ["Bash", "Write", "Edit"],
}
```

## Directory Access

```typescript
options: {
  cwd: "/projects/my-app",           // 작업 디렉토리
  additionalDirectories: [           // 추가 허용 경로
    "/shared/libs",
    "/home/user/configs"
  ],
}
```

## Permission Modes

| Mode | Description |
|------|-------------|
| `default` | 위험한 작업은 프롬프트 |
| `acceptEdits` | 파일 편집 자동 허용 |
| `dontAsk` | 프롬프트 없음, 미승인 시 거부 |
| `plan` | 계획 모드, 도구 실행 안함 |
| `bypassPermissions` | 모든 권한 우회 (위험) |

```typescript
// 안전 모드
options: { permissionMode: "dontAsk" }

// 위험 모드 (명시적 확인 필요)
options: {
  permissionMode: "bypassPermissions",
  allowDangerouslySkipPermissions: true,
}
```

## Custom Permission Handler

```typescript
options: {
  canUseTool: async (toolName, input, context) => {
    const { signal, suggestions, toolUseID, blockedPath, decisionReason } = context;

    // 거부
    return {
      behavior: "deny",
      message: "Not allowed",
      interrupt: false,  // true면 실행 중단
    };

    // 허용
    return {
      behavior: "allow",
      updatedInput: input,
      updatedPermissions: suggestions,  // 영구 권한 업데이트
    };
  }
}
```

## Common Patterns

### Read-Only Mode

```typescript
options: {
  allowedTools: ["Read", "Glob", "Grep", "WebFetch", "WebSearch"],
  disallowedTools: ["Write", "Edit", "Bash", "NotebookEdit"],
}
```

### Bash Command Filter

```typescript
canUseTool: async (toolName, input) => {
  if (toolName === "Bash") {
    const cmd = input.command as string;

    // 위험 명령 차단
    const dangerous = ["rm -rf", "sudo", "> /dev", "mkfs"];
    if (dangerous.some(d => cmd.includes(d))) {
      return { behavior: "deny", message: "Dangerous command blocked" };
    }

    // 허용된 명령만
    const allowed = ["git ", "npm ", "node ", "ls ", "cat "];
    if (!allowed.some(a => cmd.startsWith(a))) {
      return { behavior: "deny", message: "Command not in allowlist" };
    }
  }
  return { behavior: "allow", updatedInput: input };
}
```

### Path Restriction

```typescript
canUseTool: async (toolName, input) => {
  if (["Read", "Write", "Edit"].includes(toolName)) {
    const path = (input.file_path || input.path) as string;

    // 경로 순회 차단
    if (path.includes("..")) {
      return { behavior: "deny", message: "Path traversal not allowed" };
    }

    // 민감 경로 차단
    const blocked = ["/etc", "/var", "/.env", "/secrets"];
    if (blocked.some(b => path.includes(b))) {
      return { behavior: "deny", message: "Sensitive path blocked" };
    }
  }
  return { behavior: "allow", updatedInput: input };
}
```

### Logging Handler

```typescript
canUseTool: async (toolName, input, { toolUseID }) => {
  console.log(`[${toolUseID}] ${toolName}:`, JSON.stringify(input));
  return { behavior: "allow", updatedInput: input };
}
```

## Sandbox Settings

```typescript
options: {
  sandbox: {
    enabled: true,
    autoAllowBashIfSandboxed: true,
    network: {
      allowLocalBinding: true,
      allowUnixSockets: ["/var/run/docker.sock"]
    }
  }
}
```

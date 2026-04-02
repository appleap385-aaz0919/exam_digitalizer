/**
 * OctoPlayer 뷰어-콘텐츠 연동 모듈
 *
 * CBT 콘텐츠가 OctoPlayer iframe 안에서 실행될 때,
 * PostMessage를 통해 뷰어와 통신합니다.
 *
 * 참조: OctoPlayer 뷰어-콘텐츠 연동 가이드 V2 (2025-04-02)
 */

// OctoPlayer 환경인지 감지 (iframe 내부에 있는지)
export function isOctoPlayerEnv(): boolean {
  if (typeof window === 'undefined') return false;
  try {
    return window.self !== window.top;
  } catch {
    return true; // cross-origin iframe이면 OctoPlayer 가능성
  }
}

// ─── Content → Viewer 메시지 ───────────────────────────

/** xAPI 로그 + restore 데이터를 컨테이너로 전송 */
export function sendLogToContainer(data: {
  restore?: Record<string, unknown>;
  xAPI?: {
    verb: string;
    object?: { id: string; type?: string };
    result?: Record<string, unknown>;
    context?: Record<string, unknown>;
  };
}) {
  _postToParent('sendLogToContainer', data);
}

/** 콘텐츠 상태 복구 요청 */
export function requestRestoreData() {
  _postToParent('requestRestoreData', {});
}

/** 사용자 ID 요청 */
export function requestUserId() {
  _postToParent('requestUserId', {});
}

/** 현재 페이지 정보 전송 (iframe 타입) */
export function sendCurrentPage(page: number, totalPages: number, height: number) {
  _postToParent('iframeCurrentPage', {
    currentPage: page,
    totalPage: totalPages,
    height,
  });
}

// ─── Viewer → Content 메시지 수신 ──────────────────────

type OctoMessageHandler = {
  onRestoreData?: (data: { contentId: string; contentTag: string; restore: Record<string, unknown> }) => void;
  onUserId?: (userId: string) => void;
  onNextPage?: () => void;
  onPrevPage?: () => void;
  onTerminated?: () => void;
};

let _cleanup: (() => void) | null = null;

/** OctoPlayer 메시지 리스너 등록 */
export function initOctoPlayerListener(handlers: OctoMessageHandler): () => void {
  if (typeof window === 'undefined') return () => {};

  const listener = (event: MessageEvent) => {
    const { type, data } = event.data ?? {};
    switch (type) {
      case 'sendRestoreData':
        handlers.onRestoreData?.(data);
        break;
      case 'sendUserId':
        handlers.onUserId?.(data?.userId);
        break;
      case 'nextPage':
        handlers.onNextPage?.();
        break;
      case 'prevPage':
        handlers.onPrevPage?.();
        break;
      case 'terminated':
        handlers.onTerminated?.();
        break;
    }
  };

  window.addEventListener('message', listener);
  _cleanup = () => window.removeEventListener('message', listener);
  return _cleanup;
}

// ─── xAPI 이벤트 빌더 ──────────────────────────────────

/** 시험 시작 xAPI 이벤트 */
export function buildStartEvent(contentId: string, studentName: string) {
  return {
    verb: 'attempted',
    object: { id: contentId, type: 'assessment' },
    result: { duration: 'PT0S' },
    context: {
      extensions: {
        'lcms/conts-id': contentId,
        'student-name': studentName,
      },
    },
  };
}

/** 문항 응답 xAPI 이벤트 */
export function buildAnswerEvent(contentId: string, pkey: string, value: string, seq: number) {
  return {
    verb: 'answered',
    object: { id: `${contentId}_${pkey}`, type: 'question' },
    result: {
      response: value,
      extensions: { seq, pkey },
    },
    context: {
      extensions: { 'lcms/conts-id': contentId },
    },
  };
}

/** 시험 완료 xAPI 이벤트 */
export function buildCompleteEvent(
  contentId: string,
  score: number,
  maxScore: number,
  duration: string,
) {
  return {
    verb: 'completed',
    object: { id: contentId, type: 'assessment' },
    result: {
      score: { raw: score, max: maxScore },
      duration,
      completion: true,
    },
    context: {
      extensions: { 'lcms/conts-id': contentId },
    },
  };
}

// ─── 내부 유틸 ─────────────────────────────────────────

function _postToParent(type: string, data: unknown) {
  if (typeof window === 'undefined') return;
  try {
    window.parent.postMessage({ type, data }, '*');
  } catch {
    // 부모 프레임이 없거나 cross-origin 제한
  }
}

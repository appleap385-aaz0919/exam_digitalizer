'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { adminApi } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AlertCircle, CheckCircle2, XCircle, Eye, RefreshCw, ChevronRight } from 'lucide-react';

interface ReviewItem {
  pkey: string;
  seq_num: number;
  batch_id: string;
  current_stage: string;
  reject_count: number;
  reject_context: Record<string, unknown> | null;
  last_score: number | null;
  raw_text: string | null;
  render_html: string | null;
  content_html: string | null;
  answer_correct: Record<string, unknown> | null;
  answer_source: string | null;
  metadata: {
    subject: string | null;
    grade: number | null;
    unit: string | null;
    difficulty: string | null;
    question_type: string | null;
  } | null;
  updated_at: string | null;
}

export default function HumanReviewPage() {
  const queryClient = useQueryClient();
  const [selectedPkey, setSelectedPkey] = useState<string | null>(null);
  const [processing, setProcessing] = useState<Record<string, 'approve' | 'reject' | null>>({});
  const [message, setMessage] = useState<{ pkey: string; type: 'success' | 'error'; text: string } | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['humanReview'],
    queryFn: () => adminApi.listHumanReview(),
    refetchInterval: 30_000,
  });

  const items: ReviewItem[] = data?.data?.data ?? [];
  const selected = items.find((i) => i.pkey === selectedPkey) ?? null;

  const handleAction = async (pkey: string, action: 'approve' | 'reject') => {
    setProcessing((prev) => ({ ...prev, [pkey]: action }));
    setMessage(null);
    try {
      if (action === 'approve') {
        await adminApi.approveHumanReview(pkey);
        setMessage({ pkey, type: 'success', text: '승인 완료 — DATA 스테이지로 진행합니다' });
      } else {
        await adminApi.rejectHumanReview(pkey);
        setMessage({ pkey, type: 'success', text: '반려 완료 — PRODUCTION 재작업을 시작합니다' });
      }
      // 목록에서 제거 (상태 변경됨)
      setSelectedPkey(null);
      queryClient.invalidateQueries({ queryKey: ['humanReview'] });
    } catch (err: unknown) {
      const errMsg = (err as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (err as { message?: string })?.message ?? '오류가 발생했습니다';
      setMessage({ pkey, type: 'error', text: errMsg });
    } finally {
      setProcessing((prev) => ({ ...prev, [pkey]: null }));
    }
  };

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <AlertCircle className="w-6 h-6 text-amber-500" />
            검토 대기 문항
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            AI가 3회 연속 반려한 문항입니다. 사람이 직접 검토 후 승인/반려를 결정합니다.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-4 h-4 mr-1.5" />
          새로고침
        </Button>
      </div>

      {isLoading ? (
        <div className="py-20 text-center text-sm text-muted-foreground">불러오는 중...</div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-20 text-center">
            <CheckCircle2 className="w-12 h-12 mx-auto mb-3 text-emerald-400 opacity-70" />
            <p className="text-sm text-muted-foreground font-medium">검토 대기 문항이 없습니다</p>
            <p className="text-xs text-muted-foreground/60 mt-1">모든 문항이 정상 처리 중입니다</p>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-5 gap-4">
          {/* 왼쪽: 대기 목록 */}
          <Card className="col-span-2 max-h-[80vh] overflow-y-auto">
            <CardHeader className="pb-2 sticky top-0 bg-card z-10 border-b">
              <CardTitle className="text-sm flex items-center gap-2">
                <Badge variant="destructive" className="text-xs">{items.length}</Badge>
                검토 대기 문항
              </CardTitle>
            </CardHeader>
            <CardContent className="p-2">
              <div className="space-y-1">
                {items.map((item) => {
                  const isActive = selectedPkey === item.pkey;
                  const isProcessing = !!processing[item.pkey];
                  const wasActioned = message?.pkey === item.pkey && message.type === 'success';
                  return (
                    <button
                      key={item.pkey}
                      onClick={() => setSelectedPkey(item.pkey)}
                      disabled={isProcessing}
                      className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors ${
                        isActive
                          ? 'bg-amber-50 dark:bg-amber-950/30 border border-amber-200/60'
                          : 'hover:bg-accent border border-transparent'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-medium">{item.pkey}</span>
                        <ChevronRight className={`w-3.5 h-3.5 transition-colors ${isActive ? 'text-amber-500' : 'text-muted-foreground/30'}`} />
                      </div>
                      <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                        <Badge variant="outline" className="text-[10px] py-0 h-4">
                          {item.batch_id}
                        </Badge>
                        <Badge variant="secondary" className="text-[10px] py-0 h-4">
                          반려 {item.reject_count}회
                        </Badge>
                        {item.last_score !== null && (
                          <Badge
                            variant="outline"
                            className={`text-[10px] py-0 h-4 ${item.last_score < 60 ? 'text-red-500 border-red-200' : ''}`}
                          >
                            점수 {item.last_score?.toFixed(0)}
                          </Badge>
                        )}
                        {item.metadata?.question_type && (
                          <Badge variant="outline" className="text-[10px] py-0 h-4">
                            {item.metadata.question_type}
                          </Badge>
                        )}
                      </div>
                      {item.updated_at && (
                        <div className="text-[10px] text-muted-foreground/50 mt-1">
                          {new Date(item.updated_at).toLocaleString('ko-KR')}
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>

          {/* 오른쪽: 문항 상세 + 승인/반려 */}
          <div className="col-span-3">
            {selected ? (
              <div className="space-y-4">
                {/* 알림 메시지 */}
                {message?.pkey === selected.pkey && (
                  <div className={`p-3 rounded-lg text-sm flex items-start gap-2 ${
                    message.type === 'success'
                      ? 'bg-emerald-50 dark:bg-emerald-950/30 text-emerald-700 border border-emerald-200/50'
                      : 'bg-red-50 dark:bg-red-950/30 text-red-700 border border-red-200/50'
                  }`}>
                    {message.type === 'success'
                      ? <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
                      : <XCircle className="w-4 h-4 mt-0.5 shrink-0" />}
                    {message.text}
                  </div>
                )}

                {/* 문항 정보 카드 */}
                <Card>
                  <CardHeader className="pb-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <CardTitle className="text-base font-mono">{selected.pkey}</CardTitle>
                        <p className="text-xs text-muted-foreground mt-0.5">
                          {selected.batch_id} · {selected.seq_num}번 문항
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-amber-600 border-amber-300 bg-amber-50 dark:bg-amber-950/30">
                          AI 반려 {selected.reject_count}회
                        </Badge>
                        {selected.last_score !== null && (
                          <Badge variant="outline" className="text-red-500 border-red-200">
                            마지막 점수: {selected.last_score?.toFixed(1)}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* AI 반려 사유 */}
                    {selected.reject_context && (
                      <div className="p-3 bg-amber-50 dark:bg-amber-950/20 rounded-lg border border-amber-200/40">
                        <p className="text-xs font-semibold text-amber-700 mb-1">AI 반려 사유</p>
                        <p className="text-xs text-amber-600/80 font-mono break-all">
                          {typeof selected.reject_context.reason === 'string'
                            ? selected.reject_context.reason
                            : JSON.stringify(selected.reject_context)}
                        </p>
                      </div>
                    )}

                    {/* 렌더링 미리보기 */}
                    {selected.render_html ? (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground mb-2">렌더링 미리보기</p>
                        <div
                          className="render-preview p-4 border rounded-lg bg-white dark:bg-zinc-900 text-sm leading-relaxed"
                          dangerouslySetInnerHTML={{ __html: selected.render_html }}
                        />
                      </div>
                    ) : selected.content_html ? (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground mb-2">HTML 미리보기</p>
                        <div
                          className="render-preview p-4 border rounded-lg bg-white dark:bg-zinc-900 text-sm leading-relaxed"
                          dangerouslySetInnerHTML={{ __html: selected.content_html }}
                        />
                      </div>
                    ) : null}

                    {/* 원문 텍스트 */}
                    {selected.raw_text && (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground mb-2">원문 (파싱 결과)</p>
                        <div className="p-3 bg-muted/40 rounded-lg text-xs font-mono whitespace-pre-wrap leading-relaxed max-h-40 overflow-y-auto">
                          {selected.raw_text}
                        </div>
                      </div>
                    )}

                    {/* 정답 정보 */}
                    {selected.answer_correct !== null && (
                      <div className="p-3 bg-emerald-50 dark:bg-emerald-950/30 rounded-lg border border-emerald-200/50">
                        <span className="text-xs font-semibold text-emerald-700">정답</span>
                        <div className="mt-1 text-sm font-mono">
                          {JSON.stringify(selected.answer_correct)}
                        </div>
                        {selected.answer_source && (
                          <span className="text-[10px] text-emerald-600/60 mt-0.5 block">
                            출처: {selected.answer_source}
                          </span>
                        )}
                      </div>
                    )}

                    {/* 메타정보 */}
                    {selected.metadata && (
                      <div>
                        <p className="text-xs font-semibold text-muted-foreground mb-2">메타정보</p>
                        <div className="grid grid-cols-3 gap-2">
                          {Object.entries(selected.metadata).map(([k, v]) =>
                            v !== null && v !== undefined ? (
                              <div key={k} className="p-2 bg-muted/40 rounded text-xs">
                                <span className="text-muted-foreground">{k}</span>
                                <div className="font-medium mt-0.5 truncate">{String(v)}</div>
                              </div>
                            ) : null
                          )}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>

                {/* 승인 / 반려 버튼 */}
                <Card>
                  <CardContent className="p-4">
                    <p className="text-sm font-medium mb-3">이 문항을 어떻게 처리하시겠습니까?</p>
                    <div className="grid grid-cols-2 gap-3">
                      <Button
                        onClick={() => handleAction(selected.pkey, 'approve')}
                        disabled={!!processing[selected.pkey]}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white"
                      >
                        {processing[selected.pkey] === 'approve' ? (
                          <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                          <CheckCircle2 className="w-4 h-4 mr-2" />
                        )}
                        승인 — 다음 단계로 진행
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => handleAction(selected.pkey, 'reject')}
                        disabled={!!processing[selected.pkey]}
                        className="border-red-200 text-red-600 hover:bg-red-50 hover:border-red-300 dark:hover:bg-red-950/30"
                      >
                        {processing[selected.pkey] === 'reject' ? (
                          <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                        ) : (
                          <XCircle className="w-4 h-4 mr-2" />
                        )}
                        반려 — 제작 재시도
                      </Button>
                    </div>
                    <p className="text-[11px] text-muted-foreground mt-2.5 text-center">
                      승인 시 → DATA 스테이지 진행 · 반려 시 → PRODUCTION 재작업 (반려 카운트 초기화)
                    </p>
                  </CardContent>
                </Card>
              </div>
            ) : (
              <Card className="h-full min-h-[400px]">
                <CardContent className="h-full flex items-center justify-center">
                  <div className="text-center">
                    <Eye className="w-12 h-12 mx-auto mb-3 text-muted-foreground/20" />
                    <p className="text-sm text-muted-foreground">왼쪽에서 문항을 선택하세요</p>
                    <p className="text-xs text-muted-foreground/50 mt-1">원문, 렌더링, 정답, 반려 사유를 확인할 수 있습니다</p>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

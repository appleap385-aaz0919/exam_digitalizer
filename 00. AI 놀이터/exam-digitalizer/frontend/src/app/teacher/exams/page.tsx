'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { examApi, questionApi } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  ClipboardList, Plus, ArrowLeft, ChevronUp, ChevronDown, X, Eye, Search,
} from 'lucide-react';

interface CartItem {
  pkey: string;
  questionType: string;
  difficulty: string;
  points: number;
  rawText: string;
}

const DEFAULT_POINTS: Record<string, number> = {
  '객관식': 3,
  '단답형': 4,
  '서술형': 6,
  'unknown': 3,
};

function stageBadgeVariant(stage: string) {
  if (stage === 'L1_COMPLETED' || stage === 'PROD_REVIEW') return 'default';
  return 'secondary';
}

function examStatusBadge(status: string) {
  if (status === 'EXAM_CONFIRMED') return 'default';
  if (status === 'EXAM_REVIEW') return 'secondary';
  return 'outline';
}

export default function ExamsPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<'list' | 'create'>('list');
  const [cart, setCart] = useState<CartItem[]>([]);
  const [title, setTitle] = useState('');
  const [timeLimit, setTimeLimit] = useState(50);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedExamId, setSelectedExamId] = useState<string | null>(null);

  // 문항 미리보기 Dialog
  const [previewPkey, setPreviewPkey] = useState<string | null>(null);

  const exams = useQuery({ queryKey: ['exams'], queryFn: () => examApi.list({ limit: 50 }) });
  const questions = useQuery({
    queryKey: ['allQuestions'],
    queryFn: () => questionApi.list({ limit: 100 }),
  });
  const examDetail = useQuery({
    queryKey: ['examDetail', selectedExamId],
    queryFn: () => examApi.get(selectedExamId!),
    enabled: !!selectedExamId,
  });
  const previewDetail = useQuery({
    queryKey: ['questionDetail', previewPkey],
    queryFn: () => questionApi.get(previewPkey!),
    enabled: !!previewPkey,
  });

  const createMutation = useMutation({
    mutationFn: (data: {
      title: string;
      question_pkeys: string[];
      time_limit_minutes: number;
      points_per_type: Record<string, number>;
    }) => examApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['exams'] });
      setTab('list');
      setCart([]);
      setTitle('');
    },
  });
  const confirmMutation = useMutation({
    mutationFn: (id: string) => examApi.confirm(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['exams'] }),
  });

  const examList = exams.data?.data.data ?? [];
  const qList: any[] = questions.data?.data.data ?? [];
  const cartPkeys = new Set(cart.map(c => c.pkey));

  const filteredQuestions = qList.filter((q: any) => {
    if (cartPkeys.has(q.pkey)) return false;
    if (!searchQuery) return true;
    const haystack = `${q.pkey} ${q.metadata?.question_type ?? ''} ${q.metadata?.difficulty ?? ''} ${q.raw?.raw_text ?? ''}`.toLowerCase();
    return haystack.includes(searchQuery.toLowerCase());
  });

  const addToCart = (q: any) => {
    const qType = q.metadata?.question_type || 'unknown';
    setCart(prev => [...prev, {
      pkey: q.pkey,
      questionType: qType,
      difficulty: q.metadata?.difficulty || '-',
      points: DEFAULT_POINTS[qType] ?? 3,
      rawText: (q.raw?.raw_text ?? '').slice(0, 60),
    }]);
  };

  const removeFromCart = (pkey: string) => setCart(prev => prev.filter(c => c.pkey !== pkey));

  const updatePoints = (pkey: string, points: number) =>
    setCart(prev => prev.map(c => c.pkey === pkey ? { ...c, points } : c));

  const moveItem = (index: number, direction: -1 | 1) => {
    const newIndex = index + direction;
    if (newIndex < 0 || newIndex >= cart.length) return;
    setCart(prev => {
      const next = [...prev];
      [next[index], next[newIndex]] = [next[newIndex], next[index]];
      return next;
    });
  };

  const totalPoints = cart.reduce((sum, c) => sum + c.points, 0);

  const handleCreate = () => {
    if (!title.trim() || cart.length === 0) return;
    createMutation.mutate({
      title: title.trim(),
      question_pkeys: cart.map(c => c.pkey),
      time_limit_minutes: timeLimit,
      points_per_type: DEFAULT_POINTS,
    });
  };

  const previewData = previewDetail.data?.data;

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">시험지 관리</h1>
          <p className="text-muted-foreground text-sm mt-1">문항을 선택해 시험지를 구성하고 학급에 배포하세요</p>
        </div>
        <div className="flex gap-2">
          <Button
            variant={tab === 'list' ? 'default' : 'outline'}
            size="sm"
            onClick={() => { setTab('list'); setSelectedExamId(null); }}
          >
            <ClipboardList className="w-4 h-4 mr-2" />
            시험지 목록
          </Button>
          <Button
            variant={tab === 'create' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setTab('create')}
          >
            <Plus className="w-4 h-4 mr-2" />
            새 시험지 만들기
          </Button>
        </div>
      </div>

      {/* 목록 탭 */}
      {tab === 'list' && !selectedExamId && (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y">
              {examList.map((e: any) => (
                <button
                  key={e.id}
                  onClick={() => setSelectedExamId(e.id)}
                  className="w-full text-left px-6 py-4 flex items-center justify-between hover:bg-accent/50 transition-colors group"
                >
                  <div>
                    <div className="font-medium">{e.title}</div>
                    <div className="text-xs text-muted-foreground mt-0.5 font-mono">
                      {e.id} · {e.total_questions}문항 · {e.total_points}점 · {e.time_limit_minutes}분
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={examStatusBadge(e.status)}>{e.status}</Badge>
                    {e.status !== 'EXAM_CONFIRMED' && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-emerald-600 border-emerald-200 hover:bg-emerald-50 hover:border-emerald-400"
                        onClick={(ev) => { ev.stopPropagation(); confirmMutation.mutate(e.id); }}
                      >
                        확정
                      </Button>
                    )}
                  </div>
                </button>
              ))}
              {examList.length === 0 && (
                <div className="px-6 py-16 text-center text-sm text-muted-foreground">
                  <ClipboardList className="w-10 h-10 mx-auto mb-3 opacity-20" />
                  <p>시험지가 없습니다.</p>
                  <p className="text-xs mt-1">새 시험지 만들기를 눌러 문항을 선택하세요.</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 상세 보기 */}
      {tab === 'list' && selectedExamId && examDetail.data && (
        <Card>
          <CardHeader className="pb-4">
            <Button variant="ghost" size="sm" className="w-fit -ml-2 mb-2" onClick={() => setSelectedExamId(null)}>
              <ArrowLeft className="w-4 h-4 mr-1" /> 목록으로
            </Button>
            <div className="flex items-start justify-between">
              <div>
                <CardTitle>{examDetail.data.data.title}</CardTitle>
                <p className="text-xs text-muted-foreground mt-1 font-mono">
                  {examDetail.data.data.id} · {examDetail.data.data.total_questions}문항 · {examDetail.data.data.total_points}점 · {examDetail.data.data.time_limit_minutes}분
                </p>
              </div>
              <Badge variant={examStatusBadge(examDetail.data.data.status)}>
                {examDetail.data.data.status}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground text-xs">
                  <th className="py-2 w-12">#</th>
                  <th className="py-2">문항 ID</th>
                  <th className="py-2 text-right w-24">배점</th>
                  <th className="py-2 text-right w-20">미리보기</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {(examDetail.data.data.questions ?? []).map((eq: any) => (
                  <tr key={eq.seq_order} className="hover:bg-accent/30 transition-colors">
                    <td className="py-3 text-muted-foreground">{eq.seq_order}</td>
                    <td className="font-mono text-xs py-3">{eq.pkey}</td>
                    <td className="text-right font-semibold py-3">{eq.points_current}점</td>
                    <td className="text-right py-3">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0"
                        onClick={() => setPreviewPkey(eq.pkey)}
                      >
                        <Eye className="w-3.5 h-3.5" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* 새 시험지 만들기 탭 */}
      {tab === 'create' && (
        <div className="grid grid-cols-5 gap-4">
          {/* 왼쪽: 문항 선택 */}
          <div className="col-span-3">
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center gap-3">
                  <CardTitle className="text-base">문항 선택</CardTitle>
                  <div className="flex-1 relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                    <Input
                      value={searchQuery}
                      onChange={e => setSearchQuery(e.target.value)}
                      placeholder="검색 (문항ID, 유형, 난이도...)"
                      className="pl-8 h-8 text-sm"
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <div className="max-h-[60vh] overflow-y-auto divide-y">
                  {filteredQuestions.map((q: any) => (
                    <div
                      key={q.pkey}
                      className="flex items-center px-4 py-3 hover:bg-accent/30 transition-colors group"
                    >
                      <div className="flex-1 min-w-0 mr-3">
                        <div className="font-mono text-xs text-foreground/80">{q.pkey}</div>
                        <div className="text-xs text-muted-foreground truncate mt-0.5">
                          {(q.raw?.raw_text ?? '').slice(0, 80)}
                        </div>
                        <div className="flex gap-1.5 mt-1.5">
                          <Badge variant="secondary" className="text-[10px] py-0 h-4">
                            {q.metadata?.question_type || '-'}
                          </Badge>
                          <Badge variant="outline" className="text-[10px] py-0 h-4">
                            {q.metadata?.difficulty || '-'}
                          </Badge>
                          <Badge variant={stageBadgeVariant(q.current_stage)} className="text-[10px] py-0 h-4">
                            {q.current_stage}
                          </Badge>
                        </div>
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 w-8 p-0"
                          onClick={() => setPreviewPkey(q.pkey)}
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </Button>
                        <Button size="sm" className="h-8 text-xs" onClick={() => addToCart(q)}>
                          + 추가
                        </Button>
                      </div>
                    </div>
                  ))}
                  {filteredQuestions.length === 0 && (
                    <div className="px-6 py-10 text-center text-sm text-muted-foreground">
                      {qList.length === 0 ? 'HWP를 업로드하면 문항이 표시됩니다.' : '모든 문항이 장바구니에 있습니다.'}
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* 오른쪽: 장바구니 + 설정 */}
          <div className="col-span-2 space-y-4">
            {/* 시험 정보 */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">시험 정보</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Input
                  value={title}
                  onChange={e => setTitle(e.target.value)}
                  placeholder="시험지 제목 (예: 3학년 1학기 중간고사)"
                />
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">시험 시간</span>
                  <Input
                    type="number"
                    value={timeLimit}
                    onChange={e => setTimeLimit(+e.target.value)}
                    min={10}
                    max={180}
                    className="w-20 text-center"
                  />
                  <span className="text-sm text-muted-foreground">분</span>
                </div>
              </CardContent>
            </Card>

            {/* 장바구니 */}
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">장바구니 ({cart.length}문항)</CardTitle>
                  <span className="text-sm font-bold text-primary">{totalPoints}점</span>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <div className="max-h-[40vh] overflow-y-auto divide-y">
                  {cart.map((item, idx) => (
                    <div key={item.pkey} className="flex items-center gap-2 px-4 py-2.5">
                      <span className="text-muted-foreground text-xs w-5 shrink-0">{idx + 1}</span>
                      <div className="flex-1 min-w-0">
                        <div className="font-mono text-xs truncate">{item.pkey}</div>
                        <div className="flex gap-1 mt-0.5">
                          <Badge variant="secondary" className="text-[10px] py-0 h-4">{item.questionType}</Badge>
                          <Badge variant="outline" className="text-[10px] py-0 h-4">{item.difficulty}</Badge>
                        </div>
                      </div>
                      <Input
                        type="number"
                        value={item.points}
                        min={1}
                        max={30}
                        onChange={e => updatePoints(item.pkey, +e.target.value)}
                        className="w-14 text-center h-7 text-xs"
                      />
                      <span className="text-muted-foreground text-xs">점</span>
                      <div className="flex flex-col gap-0">
                        <button
                          onClick={() => moveItem(idx, -1)}
                          disabled={idx === 0}
                          className="text-muted-foreground hover:text-foreground disabled:opacity-20 leading-none"
                        >
                          <ChevronUp className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => moveItem(idx, 1)}
                          disabled={idx === cart.length - 1}
                          className="text-muted-foreground hover:text-foreground disabled:opacity-20 leading-none"
                        >
                          <ChevronDown className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                        onClick={() => removeFromCart(item.pkey)}
                      >
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  ))}
                  {cart.length === 0 && (
                    <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                      왼쪽에서 문항을 추가하세요
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* 생성 버튼 */}
            <Button
              onClick={handleCreate}
              disabled={!title.trim() || cart.length === 0 || createMutation.isPending}
              className="w-full"
              size="lg"
            >
              {createMutation.isPending ? '생성 중...' : `시험지 생성 (${cart.length}문항 · ${totalPoints}점)`}
            </Button>
          </div>
        </div>
      )}

      {/* 문항 미리보기 Dialog */}
      <Dialog open={!!previewPkey} onOpenChange={(open) => { if (!open) setPreviewPkey(null); }}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="font-mono text-sm">{previewPkey}</DialogTitle>
          </DialogHeader>

          {previewDetail.isLoading && (
            <div className="py-12 text-center text-sm text-muted-foreground">불러오는 중...</div>
          )}

          {previewData && (
            <div className="space-y-4">
              {/* 메타 배지 */}
              <div className="flex gap-2 flex-wrap">
                <Badge variant="secondary">{previewData.metadata?.question_type || '-'}</Badge>
                <Badge variant="outline">{previewData.metadata?.difficulty || '-'}</Badge>
                <Badge variant={stageBadgeVariant(previewData.current_stage)}>
                  {previewData.current_stage}
                </Badge>
                {previewData.metadata?.subject && (
                  <Badge variant="outline">{previewData.metadata.subject}</Badge>
                )}
              </div>

              {/* 렌더링 HTML (있을 때 우선) */}
              {previewData.produced?.render_html ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">렌더링 미리보기</p>
                  <div
                    className="p-4 border rounded-lg bg-card text-sm leading-relaxed"
                    dangerouslySetInnerHTML={{ __html: previewData.produced.render_html }}
                  />
                </div>
              ) : previewData.raw?.raw_text ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">원문</p>
                  <div className="p-4 bg-muted/40 rounded-lg text-sm whitespace-pre-wrap font-mono leading-relaxed">
                    {previewData.raw.raw_text}
                  </div>
                </div>
              ) : null}

              {/* 정답 */}
              {previewData.produced?.answer_correct !== undefined && (
                <div className="p-3 bg-emerald-50 dark:bg-emerald-950/30 rounded-lg border border-emerald-200/50">
                  <span className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">정답</span>
                  <div className="mt-1 text-sm">{JSON.stringify(previewData.produced.answer_correct)}</div>
                </div>
              )}

              {/* 메타정보 */}
              {previewData.metadata && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">메타정보</p>
                  <div className="grid grid-cols-3 gap-2">
                    {Object.entries(previewData.metadata).map(([k, v]: [string, any]) =>
                      v && k !== 'tags' && k !== 'learning_map_id' ? (
                        <div key={k} className="p-2 bg-muted/40 rounded text-xs">
                          <span className="text-muted-foreground">{k}</span>
                          <div className="font-medium mt-0.5 truncate">{String(v)}</div>
                        </div>
                      ) : null
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

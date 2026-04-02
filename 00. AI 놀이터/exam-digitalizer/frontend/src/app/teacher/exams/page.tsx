'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { examApi, questionApi, learningMapApi } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  ClipboardList, Plus, ArrowLeft, ChevronUp, ChevronDown, X, Eye, Search, Map,
} from 'lucide-react';

interface CartItem {
  pkey: string;
  questionType: string;
  difficulty: string;
  points: number;
  rawText: string;
}

const DEFAULT_POINTS: Record<string, number> = {
  '객관식': 3, '단답형': 4, '서술형': 6, 'unknown': 3,
};

const GRADES = [
  { label: '초2', lv: 'E', g: 2, sems: [1,2] },
  { label: '초3', lv: 'E', g: 3, sems: [1,2] },
  { label: '초4', lv: 'E', g: 4, sems: [1,2] },
  { label: '초5', lv: 'E', g: 5, sems: [1,2] },
  { label: '초6', lv: 'E', g: 6, sems: [1,2] },
  { label: '중1', lv: 'M', g: 7, sems: [0] },
  { label: '중2', lv: 'M', g: 8, sems: [0] },
  { label: '중3', lv: 'M', g: 9, sems: [0] },
  { label: '고1', lv: 'H', g: 10, sems: [0] },
];

function stageBadgeVariant(stage: string) {
  if (stage === 'L1_COMPLETED' || stage === 'PROD_REVIEW') return 'default' as const;
  return 'secondary' as const;
}
function examStatusBadge(status: string) {
  if (status === 'EXAM_CONFIRMED') return 'default' as const;
  if (status === 'EXAM_REVIEW') return 'secondary' as const;
  return 'outline' as const;
}

// 문항 행 컴포넌트 (전체 검색 + 학습맵 공통)
function QuestionRow({ q, cartPkeys, addToCart, setPreviewPkey }: {
  q: any; cartPkeys: Set<string>; addToCart: (q: any) => void; setPreviewPkey: (pkey: string) => void;
}) {
  const inCart = cartPkeys.has(q.pkey);
  return (
    <div className={`flex items-center px-3 py-2.5 transition-colors ${inCart ? 'opacity-40' : 'hover:bg-accent/30'}`}>
      <div className="flex-1 min-w-0 mr-2">
        <div className="font-mono text-xs text-foreground/80">{q.pkey}</div>
        <div className="text-xs text-muted-foreground truncate mt-0.5">
          {(q.raw?.raw_text ?? q.raw_text ?? '').slice(0, 60)}
        </div>
        <div className="flex gap-1 mt-1">
          <Badge variant="secondary" className="text-[10px] py-0 h-4">{q.metadata?.question_type || q.question_type || '-'}</Badge>
          <Badge variant="outline" className="text-[10px] py-0 h-4">{q.metadata?.difficulty || q.difficulty || '-'}</Badge>
        </div>
      </div>
      <div className="flex gap-1 shrink-0">
        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setPreviewPkey(q.pkey)}>
          <Eye className="w-3.5 h-3.5" />
        </Button>
        <Button size="sm" className="h-7 text-xs" disabled={inCart} onClick={() => addToCart(q)}>
          {inCart ? '추가됨' : '+ 추가'}
        </Button>
      </div>
    </div>
  );
}

export default function ExamsPage() {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<'list' | 'create'>('list');
  const [cart, setCart] = useState<CartItem[]>([]);
  const [title, setTitle] = useState('');
  const [timeLimit, setTimeLimit] = useState(50);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedExamId, setSelectedExamId] = useState<string | null>(null);
  const [previewPkey, setPreviewPkey] = useState<string | null>(null);
  const [questionSource, setQuestionSource] = useState<'search' | 'map'>('search');

  // 학습맵 상태
  const [gi, setGi] = useState(1);
  const [semester, setSemester] = useState(GRADES[1].sems[0]);
  const [selectedD1, setSelectedD1] = useState<string | null>(null);
  const [selectedD2, setSelectedD2] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);

  const gr = GRADES[gi];

  // queries
  const exams = useQuery({ queryKey: ['exams'], queryFn: () => examApi.list({ limit: 50 }) });
  const questions = useQuery({ queryKey: ['allQuestions'], queryFn: () => questionApi.list({ limit: 100 }) });
  const examDetail = useQuery({ queryKey: ['examDetail', selectedExamId], queryFn: () => examApi.get(selectedExamId!), enabled: !!selectedExamId });
  const previewDetail = useQuery({ queryKey: ['questionDetail', previewPkey], queryFn: () => questionApi.get(previewPkey!), enabled: !!previewPkey });

  // 학습맵 queries
  const tree = useQuery({
    queryKey: ['learningMapTree', gr.lv, gr.g, semester],
    queryFn: () => learningMapApi.getTree(gr.lv, gr.g, semester),
    enabled: questionSource === 'map',
  });
  const nodeQuestions = useQuery({
    queryKey: ['nodeQuestions', selectedNodeId],
    queryFn: () => learningMapApi.getQuestions(selectedNodeId!),
    enabled: !!selectedNodeId && questionSource === 'map',
  });

  const createMutation = useMutation({
    mutationFn: (data: { title: string; question_pkeys: string[]; time_limit_minutes: number; points_per_type: Record<string, number> }) =>
      examApi.create(data),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['exams'] }); setTab('list'); setCart([]); setTitle(''); },
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
    const h = `${q.pkey} ${q.metadata?.question_type ?? ''} ${q.metadata?.difficulty ?? ''} ${q.raw?.raw_text ?? ''}`.toLowerCase();
    return h.includes(searchQuery.toLowerCase());
  });

  // 학습맵 데이터
  const treeData: any[] = tree.data?.data.data ?? [];
  const depth2Items: any[] = selectedD1 ? treeData.find((d: any) => d.depth1_number === selectedD1)?.children ?? [] : [];
  const depth3Items: any[] = selectedD2 ? depth2Items.find((d: any) => d.depth2_number === selectedD2)?.children ?? [] : [];
  const mapQList: any[] = nodeQuestions.data?.data.data ?? [];

  const addToCart = (q: any) => {
    if (cartPkeys.has(q.pkey)) return;
    const qType = q.metadata?.question_type || q.question_type || 'unknown';
    setCart(prev => [...prev, {
      pkey: q.pkey, questionType: qType,
      difficulty: q.metadata?.difficulty || q.difficulty || '-',
      points: DEFAULT_POINTS[qType] ?? 3,
      rawText: (q.raw?.raw_text ?? q.raw_text ?? '').slice(0, 60),
    }]);
  };
  const removeFromCart = (pkey: string) => setCart(prev => prev.filter(c => c.pkey !== pkey));
  const updatePoints = (pkey: string, pts: number) => setCart(prev => prev.map(c => c.pkey === pkey ? { ...c, points: pts } : c));
  const moveItem = (i: number, d: -1 | 1) => {
    const ni = i + d;
    if (ni < 0 || ni >= cart.length) return;
    setCart(prev => { const n = [...prev]; [n[i], n[ni]] = [n[ni], n[i]]; return n; });
  };
  const totalPoints = cart.reduce((s, c) => s + c.points, 0);
  const handleCreate = () => {
    if (!title.trim() || cart.length === 0) return;
    createMutation.mutate({ title: title.trim(), question_pkeys: cart.map(c => c.pkey), time_limit_minutes: timeLimit, points_per_type: DEFAULT_POINTS });
  };

  const previewData = previewDetail.data?.data;

  const resetMap = () => { setSelectedD1(null); setSelectedD2(null); setSelectedNodeId(null); };

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">시험지 관리</h1>
          <p className="text-muted-foreground text-sm mt-1">문항을 선택해 시험지를 구성하고 학급에 배포하세요</p>
        </div>
        <div className="flex gap-2">
          <Button variant={tab === 'list' ? 'default' : 'outline'} size="sm" onClick={() => { setTab('list'); setSelectedExamId(null); }}>
            <ClipboardList className="w-4 h-4 mr-2" /> 시험지 목록
          </Button>
          <Button variant={tab === 'create' ? 'default' : 'outline'} size="sm" onClick={() => setTab('create')}>
            <Plus className="w-4 h-4 mr-2" /> 새 시험지 만들기
          </Button>
        </div>
      </div>

      {/* ── 목록 탭 ── */}
      {tab === 'list' && !selectedExamId && (
        <Card>
          <CardContent className="p-0">
            <div className="divide-y">
              {examList.map((e: any) => (
                <button key={e.id} onClick={() => setSelectedExamId(e.id)} className="w-full text-left px-6 py-4 flex items-center justify-between hover:bg-accent/50 transition-colors">
                  <div>
                    <div className="font-medium">{e.title}</div>
                    <div className="text-xs text-muted-foreground mt-0.5 font-mono">{e.id} · {e.total_questions}문항 · {e.total_points}점 · {e.time_limit_minutes}분</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant={examStatusBadge(e.status)}>{e.status}</Badge>
                    {e.status !== 'EXAM_CONFIRMED' && (
                      <Button size="sm" variant="outline" className="text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                        onClick={(ev) => { ev.stopPropagation(); confirmMutation.mutate(e.id); }}>확정</Button>
                    )}
                  </div>
                </button>
              ))}
              {examList.length === 0 && (
                <div className="px-6 py-16 text-center text-sm text-muted-foreground">
                  <ClipboardList className="w-10 h-10 mx-auto mb-3 opacity-20" />
                  <p>시험지가 없습니다.</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* ── 상세 보기 ── */}
      {tab === 'list' && selectedExamId && examDetail.data && (
        <Card>
          <CardHeader className="pb-4">
            <Button variant="ghost" size="sm" className="w-fit -ml-2 mb-2" onClick={() => setSelectedExamId(null)}>
              <ArrowLeft className="w-4 h-4 mr-1" /> 목록으로
            </Button>
            <div className="flex items-start justify-between">
              <div>
                <CardTitle>{examDetail.data.data.title}</CardTitle>
                <p className="text-xs text-muted-foreground mt-1 font-mono">{examDetail.data.data.id} · {examDetail.data.data.total_questions}문항 · {examDetail.data.data.total_points}점</p>
              </div>
              <Badge variant={examStatusBadge(examDetail.data.data.status)}>{examDetail.data.data.status}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead><tr className="border-b text-left text-muted-foreground text-xs"><th className="py-2 w-12">#</th><th>문항 ID</th><th className="text-right w-24">배점</th><th className="text-right w-20">미리보기</th></tr></thead>
              <tbody className="divide-y">
                {(examDetail.data.data.questions ?? []).map((eq: any) => (
                  <tr key={eq.seq_order} className="hover:bg-accent/30">
                    <td className="py-3 text-muted-foreground">{eq.seq_order}</td>
                    <td className="font-mono text-xs py-3">{eq.pkey}</td>
                    <td className="text-right font-semibold py-3">{eq.points_current}점</td>
                    <td className="text-right py-3"><Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={() => setPreviewPkey(eq.pkey)}><Eye className="w-3.5 h-3.5" /></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* ── 새 시험지 만들기 ── */}
      {tab === 'create' && (
        <div className="grid grid-cols-5 gap-4">
          {/* 왼쪽: 문항 선택 (검색 / 학습맵 탭) */}
          <div className="col-span-3">
            <Card>
              <CardHeader className="pb-2">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setQuestionSource('search')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      questionSource === 'search' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'
                    }`}
                  >
                    <Search className="w-3.5 h-3.5" /> 전체 검색
                  </button>
                  <button
                    onClick={() => setQuestionSource('map')}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      questionSource === 'map' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:bg-accent'
                    }`}
                  >
                    <Map className="w-3.5 h-3.5" /> 학습맵 탐색
                  </button>
                </div>
              </CardHeader>

              {/* 전체 검색 */}
              {questionSource === 'search' && (
                <>
                  <div className="px-4 pb-2">
                    <div className="relative">
                      <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                      <Input value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                        placeholder="검색 (문항ID, 유형, 난이도...)" className="pl-8 h-8 text-sm" />
                    </div>
                  </div>
                  <CardContent className="p-0">
                    <div className="max-h-[55vh] overflow-y-auto divide-y">
                      {filteredQuestions.map((q: any) => (
                        <QuestionRow key={q.pkey} q={q} cartPkeys={cartPkeys} addToCart={addToCart} setPreviewPkey={setPreviewPkey} />
                      ))}
                      {filteredQuestions.length === 0 && (
                        <div className="px-6 py-10 text-center text-sm text-muted-foreground">
                          {qList.length === 0 ? 'HWP를 업로드하면 문항이 표시됩니다.' : '검색 결과가 없습니다.'}
                        </div>
                      )}
                    </div>
                  </CardContent>
                </>
              )}

              {/* 학습맵 탐색 */}
              {questionSource === 'map' && (
                <CardContent className="pt-0">
                  {/* 학년/학기 선택 */}
                  <div className="flex gap-2 mb-3">
                    <select value={gi} onChange={e => { const i = +e.target.value; setGi(i); setSemester(GRADES[i].sems[0]); resetMap(); }}
                      className="px-2 py-1 border rounded-lg bg-background text-xs">
                      {GRADES.map((g, i) => <option key={i} value={i}>{g.label}</option>)}
                    </select>
                    {gr.sems.length > 1 && (
                      <select value={semester} onChange={e => { setSemester(+e.target.value); resetMap(); }}
                        className="px-2 py-1 border rounded-lg bg-background text-xs">
                        <option value={1}>1학기</option><option value={2}>2학기</option>
                      </select>
                    )}
                  </div>

                  {/* 단원 드릴다운 + 문항 */}
                  <div className="grid grid-cols-4 gap-2">
                    {/* 대단원 */}
                    <div className="border rounded-lg p-2 max-h-[50vh] overflow-y-auto">
                      <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1.5">대단원</p>
                      {treeData.map((d1: any) => (
                        <button key={d1.depth1_number}
                          onClick={() => { setSelectedD1(d1.depth1_number); setSelectedD2(null); setSelectedNodeId(null); }}
                          className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${
                            selectedD1 === d1.depth1_number ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
                          }`}>
                          {d1.depth1_number}. {d1.depth1_name}
                          <span className={`ml-1 font-mono text-[10px] ${selectedD1 === d1.depth1_number ? 'text-primary-foreground/60' : d1.question_count > 0 ? 'text-primary' : 'text-muted-foreground'}`}>
                            ({d1.question_count ?? 0})
                          </span>
                        </button>
                      ))}
                    </div>

                    {/* 중단원 */}
                    <div className="border rounded-lg p-2 max-h-[50vh] overflow-y-auto">
                      <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1.5">중단원</p>
                      {selectedD1 ? depth2Items.map((d2: any) => (
                        <button key={d2.depth2_number}
                          onClick={() => { setSelectedD2(d2.depth2_number); setSelectedNodeId(null); }}
                          className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${
                            selectedD2 === d2.depth2_number ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
                          }`}>
                          {d2.depth2_name || d2.depth2_number}
                          <span className={`ml-1 font-mono text-[10px] ${selectedD2 === d2.depth2_number ? 'text-primary-foreground/60' : d2.question_count > 0 ? 'text-primary' : 'text-muted-foreground'}`}>
                            ({d2.question_count ?? 0})
                          </span>
                        </button>
                      )) : <p className="text-[10px] text-muted-foreground py-3 text-center">대단원 선택</p>}
                    </div>

                    {/* 소단원 */}
                    <div className="border rounded-lg p-2 max-h-[50vh] overflow-y-auto">
                      <p className="text-[10px] font-bold text-muted-foreground uppercase mb-1.5">소단원</p>
                      {selectedD2 ? depth3Items.map((d3: any) => (
                        <button key={d3.depth3_number}
                          onClick={() => setSelectedNodeId(d3.node_id)}
                          className={`w-full text-left px-2 py-1.5 rounded text-xs transition-colors ${
                            selectedNodeId === d3.node_id ? 'bg-primary text-primary-foreground' : 'hover:bg-accent'
                          }`}>
                          {d3.depth3_name}
                          <span className={`ml-1 font-mono text-[10px] ${selectedNodeId === d3.node_id ? 'text-primary-foreground/60' : d3.question_count > 0 ? 'text-primary' : 'text-muted-foreground'}`}>
                            ({d3.question_count ?? 0})
                          </span>
                        </button>
                      )) : <p className="text-[10px] text-muted-foreground py-3 text-center">중단원 선택</p>}
                    </div>

                    {/* 문항 리스트 */}
                    <div className="border rounded-lg max-h-[50vh] overflow-y-auto">
                      <p className="text-[10px] font-bold text-muted-foreground uppercase p-2 pb-1">문항</p>
                      {selectedNodeId ? (
                        nodeQuestions.isLoading ? (
                          <p className="text-[10px] text-muted-foreground py-4 text-center">로딩...</p>
                        ) : mapQList.length > 0 ? (
                          <div className="divide-y">
                            {mapQList.map((q: any) => (
                              <QuestionRow key={q.pkey} q={q} cartPkeys={cartPkeys} addToCart={addToCart} setPreviewPkey={setPreviewPkey} />
                            ))}
                          </div>
                        ) : (
                          <p className="text-[10px] text-muted-foreground py-4 text-center">매핑된 문항 없음</p>
                        )
                      ) : (
                        <p className="text-[10px] text-muted-foreground py-4 text-center">소단원 선택</p>
                      )}
                    </div>
                  </div>
                </CardContent>
              )}
            </Card>
          </div>

          {/* 오른쪽: 장바구니 + 설정 */}
          <div className="col-span-2 space-y-4">
            <Card>
              <CardHeader className="pb-3"><CardTitle className="text-base">시험 정보</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <Input value={title} onChange={e => setTitle(e.target.value)} placeholder="시험지 제목 (예: 3학년 1학기 중간고사)" />
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">시험 시간</span>
                  <Input type="number" value={timeLimit} onChange={e => setTimeLimit(+e.target.value)} min={10} max={180} className="w-20 text-center" />
                  <span className="text-sm text-muted-foreground">분</span>
                </div>
              </CardContent>
            </Card>

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
                      <Input type="number" value={item.points} min={1} max={30}
                        onChange={e => updatePoints(item.pkey, +e.target.value)} className="w-14 text-center h-7 text-xs" />
                      <span className="text-muted-foreground text-xs">점</span>
                      <div className="flex flex-col gap-0">
                        <button onClick={() => moveItem(idx, -1)} disabled={idx === 0} className="text-muted-foreground hover:text-foreground disabled:opacity-20 leading-none"><ChevronUp className="w-3.5 h-3.5" /></button>
                        <button onClick={() => moveItem(idx, 1)} disabled={idx === cart.length - 1} className="text-muted-foreground hover:text-foreground disabled:opacity-20 leading-none"><ChevronDown className="w-3.5 h-3.5" /></button>
                      </div>
                      <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-destructive hover:text-destructive" onClick={() => removeFromCart(item.pkey)}>
                        <X className="w-3.5 h-3.5" />
                      </Button>
                    </div>
                  ))}
                  {cart.length === 0 && <div className="px-4 py-8 text-center text-sm text-muted-foreground">문항을 추가하세요</div>}
                </div>
              </CardContent>
            </Card>

            <Button onClick={handleCreate} disabled={!title.trim() || cart.length === 0 || createMutation.isPending} className="w-full" size="lg">
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
          {previewDetail.isLoading && <div className="py-12 text-center text-sm text-muted-foreground">불러오는 중...</div>}
          {previewData && (
            <div className="space-y-4">
              <div className="flex gap-2 flex-wrap">
                <Badge variant="secondary">{previewData.metadata?.question_type || '-'}</Badge>
                <Badge variant="outline">{previewData.metadata?.difficulty || '-'}</Badge>
                <Badge variant={stageBadgeVariant(previewData.current_stage)}>{previewData.current_stage}</Badge>
              </div>
              {previewData.produced?.render_html ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">렌더링 미리보기</p>
                  <div className="p-4 border rounded-lg bg-card text-sm leading-relaxed" dangerouslySetInnerHTML={{ __html: previewData.produced.render_html }} />
                </div>
              ) : previewData.raw?.raw_text ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">원문</p>
                  <div className="p-4 bg-muted/40 rounded-lg text-sm whitespace-pre-wrap font-mono leading-relaxed">{previewData.raw.raw_text}</div>
                </div>
              ) : null}
              {previewData.produced?.answer_correct !== undefined && (
                <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-200/50">
                  <span className="text-xs font-semibold text-emerald-700">정답</span>
                  <div className="mt-1 text-sm">{JSON.stringify(previewData.produced.answer_correct)}</div>
                </div>
              )}
              {previewData.metadata && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">메타정보</p>
                  <div className="grid grid-cols-3 gap-2">
                    {Object.entries(previewData.metadata).map(([k, v]: [string, any]) =>
                      v && k !== 'tags' && k !== 'learning_map_id' ? (
                        <div key={k} className="p-2 bg-muted/40 rounded text-xs"><span className="text-muted-foreground">{k}</span><div className="font-medium mt-0.5 truncate">{String(v)}</div></div>
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

'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { learningMapApi, questionApi } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Eye } from 'lucide-react';

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

export default function LearningMapsPage() {
  const [gi, setGi] = useState(1);
  const gr = GRADES[gi];
  const [semester, setSemester] = useState(gr.sems[0]);
  const [selectedD1, setSelectedD1] = useState<string | null>(null);
  const [selectedD2, setSelectedD2] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);
  const [previewPkey, setPreviewPkey] = useState<string | null>(null);

  const tree = useQuery({
    queryKey: ['learningMapTree', gr.lv, gr.g, semester],
    queryFn: () => learningMapApi.getTree(gr.lv, gr.g, semester),
  });
  const questions = useQuery({
    queryKey: ['nodeQuestions', selectedNodeId],
    queryFn: () => learningMapApi.getQuestions(selectedNodeId!),
    enabled: !!selectedNodeId,
  });
  const previewDetail = useQuery({
    queryKey: ['questionDetail', previewPkey],
    queryFn: () => questionApi.get(previewPkey!),
    enabled: !!previewPkey,
  });

  const treeData: any[] = tree.data?.data.data ?? [];
  const selectedD1Data = selectedD1 ? treeData.find((d: any) => d.depth1_number === selectedD1) : null;
  const depth2Items: any[] = selectedD1Data?.children ?? [];
  const selectedD2Data = selectedD2 ? depth2Items.find((d: any) => d.depth2_number === selectedD2) : null;
  const depth3Items: any[] = selectedD2Data?.children ?? [];
  // 소단원이 없는 중단원은 node_id를 직접 가짐
  const d2NodeId = selectedD2Data?.node_id ?? null;

  const reset = () => { setSelectedD1(null); setSelectedD2(null); setSelectedNodeId(null); };

  const previewData = previewDetail.data?.data;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">학습맵 탐색</h1>
        <p className="text-muted-foreground text-sm mt-1">교과 단원 트리에서 문항을 탐색하세요</p>
      </div>

      <div className="flex gap-3 flex-wrap">
        <select
          value={gi}
          onChange={(e) => { const i = +e.target.value; setGi(i); setSemester(GRADES[i].sems[0]); reset(); }}
          className="px-3 py-2 border rounded-lg bg-background text-sm"
        >
          {GRADES.map((g, i) => <option key={i} value={i}>{g.label}</option>)}
        </select>
        {gr.sems.length > 1 ? (
          <select
            value={semester}
            onChange={(e) => { setSemester(+e.target.value); reset(); }}
            className="px-3 py-2 border rounded-lg bg-background text-sm"
          >
            <option value={1}>1학기</option>
            <option value={2}>2학기</option>
          </select>
        ) : (
          <span className="px-3 py-2 text-sm text-muted-foreground">(학기 구분 없음)</span>
        )}
      </div>

      <div className="grid grid-cols-4 gap-4">
        {/* Depth1 대단원 */}
        <div className="bg-card rounded-xl border p-4 max-h-[70vh] overflow-y-auto">
          <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wide mb-3">대단원</h3>
          <div className="space-y-1">
            {treeData.map((d1: any) => (
              <button
                key={d1.depth1_number}
                onClick={() => { setSelectedD1(d1.depth1_number); setSelectedD2(null); setSelectedNodeId(null); }}
                className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                  selectedD1 === d1.depth1_number
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-accent'
                }`}
              >
                <span>{d1.depth1_number}. {d1.depth1_name}</span>
                <span className={`text-xs ml-1.5 font-mono ${
                  selectedD1 === d1.depth1_number ? 'text-primary-foreground/60'
                  : d1.question_count > 0 ? 'text-primary' : 'text-muted-foreground'
                }`}>({d1.question_count ?? 0})</span>
              </button>
            ))}
          </div>
        </div>

        {/* Depth2 중단원 */}
        <div className="bg-card rounded-xl border p-4 max-h-[70vh] overflow-y-auto">
          <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wide mb-3">중단원</h3>
          {selectedD1 ? (
            <div className="space-y-1">
              {depth2Items.map((d2: any) => (
                <button
                  key={d2.depth2_number}
                  onClick={() => {
                    setSelectedD2(d2.depth2_number);
                    // 소단원이 없고 중단원에 node_id가 있으면 바로 문항 표시
                    if ((d2.children ?? []).length === 0 && d2.node_id) {
                      setSelectedNodeId(d2.node_id);
                    } else {
                      setSelectedNodeId(null);
                    }
                  }}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    selectedD2 === d2.depth2_number
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-accent'
                  }`}
                >
                  <span>{d2.depth2_name || d2.depth2_number}</span>
                  <span className={`text-xs ml-1.5 font-mono ${
                    selectedD2 === d2.depth2_number ? 'text-primary-foreground/60'
                    : d2.question_count > 0 ? 'text-primary' : 'text-muted-foreground'
                  }`}>({d2.question_count ?? 0})</span>
                </button>
              ))}
            </div>
          ) : <p className="text-xs text-muted-foreground">대단원을 선택하세요</p>}
        </div>

        {/* Depth3 소단원 */}
        <div className="bg-card rounded-xl border p-4 max-h-[70vh] overflow-y-auto">
          <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wide mb-3">소단원</h3>
          {selectedD2 ? (
            <div className="space-y-1">
              {depth3Items.length > 0 ? depth3Items.map((d3: any) => (
                <button
                  key={d3.depth3_number}
                  onClick={() => setSelectedNodeId(d3.node_id)}
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                    selectedNodeId === d3.node_id
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-accent'
                  }`}
                >
                  <span>{d3.depth3_name}</span>
                  <span className={`text-xs ml-1.5 font-mono ${
                    selectedNodeId === d3.node_id ? 'text-primary-foreground/60'
                    : d3.question_count > 0 ? 'text-primary' : 'text-muted-foreground'
                  }`}>({d3.question_count ?? 0})</span>
                </button>
              )) : d2NodeId ? (
                <p className="text-xs text-muted-foreground">소단원 없음 — 중단원에 직접 매핑됩니다</p>
              ) : <p className="text-xs text-muted-foreground">소단원이 없습니다</p>}
            </div>
          ) : <p className="text-xs text-muted-foreground">중단원을 선택하세요</p>}
        </div>

        {/* 문항 리스트 */}
        <div className="bg-card rounded-xl border p-4 max-h-[70vh] overflow-y-auto">
          <h3 className="text-xs font-bold text-muted-foreground uppercase tracking-wide mb-3">
            문항 {questions.data ? `(${questions.data.data.meta?.total ?? 0})` : ''}
          </h3>
          {selectedNodeId ? (
            questions.isLoading ? (
              <p className="text-xs text-muted-foreground">로딩 중...</p>
            ) : (
              <div className="space-y-2">
                {(questions.data?.data.data ?? []).map((q: any) => (
                  <button
                    key={q.pkey}
                    onClick={() => setPreviewPkey(q.pkey)}
                    className="w-full p-3 border rounded-lg text-xs text-left hover:bg-accent hover:border-primary/30 transition-colors group"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="font-mono text-primary text-[11px]">{q.pkey}</span>
                      <Eye className="w-3.5 h-3.5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <div className="flex gap-1.5 flex-wrap">
                      <Badge variant="secondary" className="text-[10px] py-0 h-4">{q.question_type}</Badge>
                      <Badge variant="outline" className="text-[10px] py-0 h-4">{q.difficulty}</Badge>
                      {q.achievement_code && (
                        <Badge variant="outline" className="text-[10px] py-0 h-4 text-emerald-700 border-emerald-200">
                          {q.achievement_code}
                        </Badge>
                      )}
                    </div>
                  </button>
                ))}
                {(questions.data?.data.data ?? []).length === 0 && (
                  <p className="text-xs text-muted-foreground py-4">
                    매핑된 문항이 없습니다.
                    <br /><br />
                    HWP 업로드 후 파이프라인 완료 시 표시됩니다.
                  </p>
                )}
              </div>
            )
          ) : (
            <p className="text-xs text-muted-foreground">단원을 선택하세요</p>
          )}
        </div>
      </div>

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
              <div className="flex gap-2 flex-wrap">
                <Badge variant="secondary">{previewData.metadata?.question_type || '-'}</Badge>
                <Badge variant="outline">{previewData.metadata?.difficulty || '-'}</Badge>
                <Badge variant={
                  previewData.current_stage === 'L1_COMPLETED' || previewData.current_stage === 'PROD_REVIEW'
                    ? 'default' : 'secondary'
                }>{previewData.current_stage}</Badge>
                {previewData.metadata?.subject && (
                  <Badge variant="outline">{previewData.metadata.subject}</Badge>
                )}
              </div>

              {previewData.produced?.render_html ? (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-2">렌더링 미리보기</p>
                  <div
                    className="render-preview p-4 border rounded-lg bg-card text-sm leading-relaxed"
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

              {previewData.produced?.answer_correct !== undefined && (
                <div className="p-3 bg-emerald-50 dark:bg-emerald-950/30 rounded-lg border border-emerald-200/50">
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

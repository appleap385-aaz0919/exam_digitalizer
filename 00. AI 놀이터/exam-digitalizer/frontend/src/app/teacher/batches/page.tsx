'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { batchApi, questionApi } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Upload, FileUp, ArrowLeft, Eye, ChevronRight } from 'lucide-react';

export default function BatchesPage() {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [selectedBatchId, setSelectedBatchId] = useState<string | null>(null);
  const [previewPkey, setPreviewPkey] = useState<string | null>(null);

  const batches = useQuery({ queryKey: ['batches'], queryFn: () => batchApi.list() });
  const batchQuestions = useQuery({
    queryKey: ['batchQuestions', selectedBatchId],
    queryFn: () => batchApi.getQuestions(selectedBatchId!, 1),
    enabled: !!selectedBatchId,
  });
  const previewDetail = useQuery({
    queryKey: ['questionDetail', previewPkey],
    queryFn: () => questionApi.get(previewPkey!),
    enabled: !!previewPkey,
  });

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const res = await batchApi.upload(file);
      setUploadResult(`배치 ${res.data.batch_id} 생성 — 파싱 시작됨`);
      setFile(null);
      queryClient.invalidateQueries({ queryKey: ['batches'] });
    } catch (err: any) {
      setUploadResult(`업로드 실패: ${err.response?.data?.detail || err.message}`);
    } finally {
      setUploading(false);
    }
  };

  const batchList = batches.data?.data.data ?? [];
  const qList: any[] = batchQuestions.data?.data.data ?? [];
  const previewData = previewDetail.data?.data;

  // 배치 상세 보기
  if (selectedBatchId) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => setSelectedBatchId(null)}>
            <ArrowLeft className="w-4 h-4 mr-1" /> 목록으로
          </Button>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">배치 문항 상세</h1>
            <p className="text-muted-foreground text-sm mt-0.5 font-mono">{selectedBatchId}</p>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          {/* 문항 리스트 */}
          <Card className="max-h-[78vh] overflow-y-auto">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-muted-foreground">
                파싱된 문항 ({batchQuestions.data?.data.meta?.total ?? qList.length})
              </CardTitle>
            </CardHeader>
            <CardContent className="p-2">
              {batchQuestions.isLoading && (
                <p className="text-xs text-muted-foreground py-8 text-center">불러오는 중...</p>
              )}
              <div className="space-y-1">
                {qList.map((q: any) => (
                  <button
                    key={q.pkey}
                    onClick={() => setPreviewPkey(q.pkey)}
                    className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition-colors group ${
                      previewPkey === q.pkey
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-accent'
                    }`}
                  >
                    <div className="font-mono text-xs">{q.pkey}</div>
                    <div className="flex gap-1.5 mt-1">
                      <Badge
                        variant={previewPkey === q.pkey ? 'outline' : 'secondary'}
                        className={`text-[10px] py-0 h-4 ${previewPkey === q.pkey ? 'border-primary-foreground/40 text-primary-foreground' : ''}`}
                      >
                        {q.metadata?.question_type || '-'}
                      </Badge>
                      <Badge
                        variant="outline"
                        className={`text-[10px] py-0 h-4 ${previewPkey === q.pkey ? 'border-primary-foreground/40 text-primary-foreground' : ''}`}
                      >
                        {q.metadata?.difficulty || '-'}
                      </Badge>
                      <Badge
                        variant={previewPkey === q.pkey ? 'outline' : (
                          q.current_stage === 'PROD_REVIEW' || q.current_stage === 'L1_COMPLETED' ? 'default' : 'secondary'
                        )}
                        className={`text-[10px] py-0 h-4 ${previewPkey === q.pkey ? 'border-primary-foreground/40 text-primary-foreground' : ''}`}
                      >
                        {q.current_stage}
                      </Badge>
                    </div>
                  </button>
                ))}
              </div>
              {qList.length === 0 && !batchQuestions.isLoading && (
                <p className="text-xs text-muted-foreground py-8 text-center">
                  파싱 중이거나 문항이 없습니다.
                </p>
              )}
            </CardContent>
          </Card>

          {/* 문항 상세 미리보기 */}
          <div className="col-span-2">
            <Card className="max-h-[78vh] overflow-y-auto">
              <CardContent className="p-6">
                {previewPkey && previewData ? (
                  <div className="space-y-4">
                    <div className="flex items-center justify-between">
                      <h2 className="font-mono text-sm font-bold">{previewData.pkey}</h2>
                      <Badge>{previewData.current_stage}</Badge>
                    </div>

                    {/* 렌더링 HTML 미리보기 */}
                    {previewData.produced?.render_html ? (
                      <div>
                        <p className="text-xs font-medium text-muted-foreground mb-2">렌더링 미리보기</p>
                        <div
                          className="render-preview p-4 border rounded-lg bg-card text-sm leading-relaxed"
                          dangerouslySetInnerHTML={{ __html: previewData.produced.render_html }}
                        />
                      </div>
                    ) : null}

                    {/* 원문 */}
                    {previewData.raw?.raw_text ? (
                      <div>
                        <p className="text-xs font-medium text-muted-foreground mb-2">원문 (파싱 결과)</p>
                        <div className="p-4 bg-muted/40 rounded-lg text-sm whitespace-pre-wrap font-mono leading-relaxed">
                          {previewData.raw.raw_text}
                        </div>
                      </div>
                    ) : null}

                    {/* 정답 */}
                    {previewData.produced?.answer_correct !== undefined && (
                      <div className="p-3 bg-emerald-50 dark:bg-emerald-950/30 rounded-lg border border-emerald-200/50">
                        <span className="text-xs font-semibold text-emerald-700">정답</span>
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
                        {previewData.metadata?.tags && (
                          <div className="flex gap-1 mt-2 flex-wrap">
                            {(previewData.metadata.tags as string[]).map((t: string, i: number) => (
                              <Badge key={i} variant="secondary" className="text-xs">{t}</Badge>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ) : previewPkey && previewDetail.isLoading ? (
                  <div className="py-20 text-center text-sm text-muted-foreground">불러오는 중...</div>
                ) : (
                  <div className="py-20 text-center text-muted-foreground text-sm">
                    <Eye className="w-10 h-10 mx-auto mb-3 opacity-15" />
                    <p>왼쪽에서 문항을 선택하면 미리보기가 표시됩니다</p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    );
  }

  // 메인 (업로드 + 배치 목록)
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">HWP 파일 업로드</h1>
        <p className="text-muted-foreground text-sm mt-1">시험지를 올리면 AI가 자동으로 문항을 추출합니다</p>
      </div>

      <Card>
        <CardContent className="p-6">
          <div
            className={`border-2 border-dashed rounded-xl p-10 text-center transition-colors ${
              dragOver ? 'border-primary bg-primary/5' : 'border-muted-foreground/20 hover:border-primary/40'
            }`}
            onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); setDragOver(true); }}
            onDragLeave={(e) => { e.preventDefault(); e.stopPropagation(); setDragOver(false); }}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setDragOver(false);
              const dropped = e.dataTransfer.files?.[0];
              if (dropped && /\.(hwp|hwpx|hwpml)$/i.test(dropped.name)) {
                setFile(dropped);
              }
            }}
          >
            <input type="file" accept=".hwp,.hwpx,.hwpml"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="hidden" id="hwp-upload" />
            <label htmlFor="hwp-upload" className="cursor-pointer">
              <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                {file ? file.name : dragOver ? '여기에 놓으세요!' : 'HWP / HWPX / HWPML 파일을 선택하세요'}
              </p>
              <p className="text-xs text-muted-foreground/50 mt-1">또는 여기로 파일을 끌어놓으세요</p>
            </label>
          </div>
          {file && (
            <Button onClick={handleUpload} disabled={uploading} className="mt-4 w-full">
              <FileUp className="w-4 h-4 mr-2" />
              {uploading ? '업로드 중...' : '업로드 및 파싱 시작'}
            </Button>
          )}
          {uploadResult && (
            <div className={`mt-3 p-3 rounded-lg text-sm ${
              uploadResult.includes('실패') ? 'bg-destructive/10 text-destructive' : 'bg-emerald-50 text-emerald-700'
            }`}>
              {uploadResult}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">업로드 이력</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="divide-y">
            {batchList.map((b: any) => (
              <button
                key={b.id}
                onClick={() => setSelectedBatchId(b.id)}
                className="w-full text-left px-6 py-4 flex items-center justify-between hover:bg-accent/50 transition-colors group"
              >
                <div>
                  <span className="font-mono text-sm font-medium">{b.id}</span>
                  <span className="text-xs text-muted-foreground ml-2">{b.subject}</span>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    {b.total_questions}문항 추출
                    {b.created_at && ` · ${new Date(b.created_at).toLocaleString('ko-KR')}`}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <Badge variant={
                    b.status === 'COMPLETED' ? 'default' :
                    b.status === 'PARSING' ? 'secondary' : 'outline'
                  }>{b.status}</Badge>
                  <ChevronRight className="w-4 h-4 text-muted-foreground/30 group-hover:text-muted-foreground transition-colors" />
                </div>
              </button>
            ))}
            {batchList.length === 0 && (
              <div className="px-6 py-10 text-center text-sm text-muted-foreground">
                업로드된 배치가 없습니다
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

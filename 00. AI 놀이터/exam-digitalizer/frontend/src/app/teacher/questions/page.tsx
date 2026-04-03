'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { questionApi } from '@/lib/api';

export default function QuestionsPage() {
  const [selectedPkey, setSelectedPkey] = useState<string | null>(null);

  const questions = useQuery({
    queryKey: ['questions'],
    queryFn: () => questionApi.list({ limit: 50 }),
  });

  const detail = useQuery({
    queryKey: ['questionDetail', selectedPkey],
    queryFn: () => questionApi.get(selectedPkey!),
    enabled: !!selectedPkey,
  });

  const qList = questions.data?.data.data ?? [];
  const qDetail = detail.data?.data;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">제작된 문항</h1>

      <div className="grid grid-cols-3 gap-4">
        {/* 문항 목록 */}
        <div className="bg-white rounded-xl border p-4 max-h-[75vh] overflow-y-auto">
          <h3 className="text-sm font-bold text-gray-500 mb-3">
            문항 목록 ({questions.data?.data.meta?.total ?? 0})
          </h3>
          <div className="space-y-1">
            {qList.map((q: any) => (
              <button key={q.pkey} onClick={() => setSelectedPkey(q.pkey)}
                className={`w-full text-left px-3 py-2.5 rounded-lg text-sm transition border ${
                  selectedPkey === q.pkey
                    ? 'bg-primary text-white border-primary'
                    : 'hover:bg-gray-50 border-transparent'
                }`}>
                <div className="font-mono text-xs">{q.pkey}</div>
                <div className="flex gap-1.5 mt-1">
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    selectedPkey === q.pkey ? 'bg-blue-400' : 'bg-blue-100 text-blue-700'
                  }`}>{q.metadata?.question_type || '-'}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    selectedPkey === q.pkey ? 'bg-yellow-400' : 'bg-yellow-100 text-yellow-700'
                  }`}>{q.metadata?.difficulty || '-'}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                    selectedPkey === q.pkey ? 'bg-green-400' :
                    q.current_stage === 'PROD_REVIEW' || q.current_stage === 'L1_COMPLETED'
                      ? 'bg-green-100 text-green-700'
                      : 'bg-gray-100 text-gray-500'
                  }`}>{q.current_stage}</span>
                </div>
              </button>
            ))}
            {qList.length === 0 && (
              <p className="text-xs text-gray-400 py-4 text-center">
                HWP를 업로드하면 파싱된 문항이 여기에 표시됩니다.
              </p>
            )}
          </div>
        </div>

        {/* 문항 상세 */}
        <div className="col-span-2 bg-white rounded-xl border p-6 max-h-[75vh] overflow-y-auto">
          {selectedPkey && qDetail ? (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-bold text-lg">{qDetail.pkey}</h2>
                <span className="text-xs px-2 py-1 bg-gray-100 rounded">{qDetail.current_stage}</span>
              </div>

              {/* 원문 */}
              {qDetail.raw && (
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-gray-500 mb-2">원문 (파싱 결과)</h3>
                  <div className="p-4 bg-gray-50 rounded-lg text-sm whitespace-pre-wrap">
                    {qDetail.raw.raw_text}
                  </div>
                </div>
              )}

              {/* 메타정보 */}
              {qDetail.metadata && (
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-gray-500 mb-2">메타정보</h3>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    {Object.entries(qDetail.metadata).map(([k, v]: [string, any]) => (
                      v && k !== 'tags' && k !== 'learning_map_id' ? (
                        <div key={k} className="p-2 bg-gray-50 rounded">
                          <span className="text-gray-400">{k}</span>
                          <div className="font-medium mt-0.5">{String(v)}</div>
                        </div>
                      ) : null
                    ))}
                  </div>
                  {qDetail.metadata.tags && (
                    <div className="flex gap-1 mt-2">
                      {(qDetail.metadata.tags as string[]).map((t: string, i: number) => (
                        <span key={i} className="text-xs px-2 py-0.5 bg-primary-light text-primary rounded-full">{t}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* 제작 결과 */}
              {qDetail.produced && (
                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-gray-500 mb-2">제작 결과</h3>
                  <div className="space-y-2 text-sm">
                    {/* 렌더링 HTML 인라인 미리보기 (있을 때 우선) */}
                    {qDetail.produced.render_html ? (
                      <div className="p-4 border rounded-lg bg-white">
                        <span className="text-xs text-gray-500 font-medium block mb-2">렌더링 미리보기</span>
                        <div
                          className="render-preview leading-relaxed"
                          dangerouslySetInnerHTML={{ __html: qDetail.produced.render_html }}
                        />
                      </div>
                    ) : null}
                    <div className="p-3 bg-green-50 rounded-lg">
                      <span className="text-xs text-green-600 font-medium">정답</span>
                      <div className="mt-1">{JSON.stringify(qDetail.produced.answer_correct)}</div>
                    </div>
                    {qDetail.produced.answer_source && (
                      <div className="p-3 bg-blue-50 rounded-lg">
                        <span className="text-xs text-blue-600 font-medium">정답 출처</span>
                        <div className="mt-1">{qDetail.produced.answer_source}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">
              왼쪽에서 문항을 선택하세요
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

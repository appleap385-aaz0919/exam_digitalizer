'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { classroomApi, gradeApi } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { BarChart3, Users, TrendingUp, TrendingDown, Award } from 'lucide-react';

export default function GradesPage() {
  const [selectedClassroom, setSelectedClassroom] = useState<string>('');
  const [selectedCeId, setSelectedCeId] = useState<string>('');

  const classrooms = useQuery({ queryKey: ['classrooms'], queryFn: () => classroomApi.list() });
  const classExams = useQuery({
    queryKey: ['classExams', selectedClassroom],
    queryFn: () => classroomApi.listExams(selectedClassroom),
    enabled: !!selectedClassroom,
  });
  const summary = useQuery({
    queryKey: ['gradeSummary', selectedCeId],
    queryFn: () => gradeApi.classroomExamSummary(+selectedCeId),
    enabled: !!selectedCeId,
  });

  const classList = classrooms.data?.data.data ?? [];
  const ceList = classExams.data?.data.data ?? [];
  const summaryData = summary.data?.data;

  const stats = summaryData ? [
    {
      label: '응시 인원',
      value: `${summaryData.submitted_count ?? 0}명`,
      sub: `전체 ${summaryData.total_students ?? 0}명`,
      icon: Users,
      color: 'text-blue-600 bg-blue-50',
    },
    {
      label: '평균 점수',
      value: `${(summaryData.avg_score ?? 0).toFixed(1)}점`,
      sub: `총점 ${summaryData.total_points ?? 100}점`,
      icon: BarChart3,
      color: 'text-violet-600 bg-violet-50',
    },
    {
      label: '최고 점수',
      value: `${summaryData.max_score ?? 0}점`,
      sub: '',
      icon: TrendingUp,
      color: 'text-emerald-600 bg-emerald-50',
    },
    {
      label: '최저 점수',
      value: `${summaryData.min_score ?? 0}점`,
      sub: '',
      icon: TrendingDown,
      color: 'text-amber-600 bg-amber-50',
    },
  ] : [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">성적 조회</h1>
        <p className="text-muted-foreground text-sm mt-1">학급과 시험을 선택하면 성적 데이터가 표시됩니다</p>
      </div>

      {/* 필터 */}
      <div className="flex gap-3">
        <select
          value={selectedClassroom}
          onChange={e => { setSelectedClassroom(e.target.value); setSelectedCeId(''); }}
          className="h-9 px-3 rounded-lg border bg-background text-sm min-w-[200px]"
        >
          <option value="">학급 선택...</option>
          {classList.map((c: any) => (
            <option key={c.id} value={c.id}>{c.name} ({c.grade}학년)</option>
          ))}
        </select>

        {selectedClassroom && (
          <select
            value={selectedCeId}
            onChange={e => setSelectedCeId(e.target.value)}
            className="h-9 px-3 rounded-lg border bg-background text-sm min-w-[220px]"
          >
            <option value="">시험 선택...</option>
            {ceList.map((ce: any) => (
              <option key={ce.id} value={String(ce.id)}>
                {ce.exam_title || ce.exam_id}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* 빈 상태 */}
      {!selectedClassroom && (
        <Card>
          <CardContent className="py-20 text-center">
            <BarChart3 className="w-12 h-12 mx-auto mb-4 text-muted-foreground/20" />
            <p className="text-muted-foreground text-sm">학급과 시험을 선택하면 성적 데이터가 표시됩니다.</p>
          </CardContent>
        </Card>
      )}

      {selectedClassroom && !selectedCeId && (
        <Card>
          <CardContent className="py-14 text-center text-muted-foreground text-sm">
            {ceList.length === 0
              ? '이 학급에 배포된 시험이 없습니다.'
              : '시험을 선택하세요.'}
          </CardContent>
        </Card>
      )}

      {/* 로딩 */}
      {selectedCeId && summary.isLoading && (
        <Card>
          <CardContent className="py-14 text-center text-muted-foreground text-sm">로딩 중...</CardContent>
        </Card>
      )}

      {/* 에러 */}
      {selectedCeId && summary.isError && (
        <Card>
          <CardContent className="py-14 text-center">
            <p className="text-destructive text-sm mb-2">데이터를 불러올 수 없습니다.</p>
            <p className="text-xs text-muted-foreground">아직 채점이 완료되지 않았거나 배포된 시험이 없습니다.</p>
          </CardContent>
        </Card>
      )}

      {/* 성적 데이터 */}
      {selectedCeId && summaryData && (
        <div className="space-y-4">
          {/* 통계 카드 */}
          <div className="grid grid-cols-4 gap-4">
            {stats.map((s) => {
              const Icon = s.icon;
              return (
                <Card key={s.label}>
                  <CardContent className="p-5">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs text-muted-foreground">{s.label}</p>
                        <p className="text-2xl font-bold mt-1">{s.value}</p>
                        {s.sub && <p className="text-xs text-muted-foreground mt-0.5">{s.sub}</p>}
                      </div>
                      <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${s.color}`}>
                        <Icon className="w-5 h-5" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>

          {/* 학생별 성적 테이블 */}
          <Card>
            <CardHeader className="pb-0">
              <CardTitle className="text-base flex items-center gap-2">
                <Award className="w-4 h-4" />
                학생별 성적
              </CardTitle>
            </CardHeader>
            <CardContent className="p-0 mt-4">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="px-6 py-3 w-10">#</th>
                    <th className="px-3 py-3">이름</th>
                    <th className="px-3 py-3 text-right">점수</th>
                    <th className="px-3 py-3 text-right">정답률</th>
                    <th className="px-3 py-3">상태</th>
                    <th className="px-6 py-3 text-right">제출 시각</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {(summaryData.submissions ?? []).map((sub: any, i: number) => {
                    const pct = summaryData.total_points > 0
                      ? Math.round((sub.score ?? 0) / summaryData.total_points * 100)
                      : 0;
                    return (
                      <tr key={sub.id ?? i} className="hover:bg-accent/30 transition-colors">
                        <td className="px-6 py-3.5 text-muted-foreground text-xs">{i + 1}</td>
                        <td className="px-3 py-3.5 font-medium">{sub.student_name}</td>
                        <td className="px-3 py-3.5 text-right font-mono font-semibold">{sub.score ?? '-'}</td>
                        <td className="px-3 py-3.5 text-right">
                          <Badge variant={pct >= 80 ? 'default' : pct >= 50 ? 'secondary' : 'destructive'}>
                            {pct}%
                          </Badge>
                        </td>
                        <td className="px-3 py-3.5">
                          <Badge variant={
                            sub.status === 'graded' ? 'default' :
                            sub.status === 'submitted' ? 'secondary' : 'outline'
                          }>
                            {sub.status ?? '미응시'}
                          </Badge>
                        </td>
                        <td className="px-6 py-3.5 text-right text-xs text-muted-foreground">
                          {sub.submitted_at ? new Date(sub.submitted_at).toLocaleString('ko-KR') : '-'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {(summaryData.submissions ?? []).length === 0 && (
                <div className="px-6 py-14 text-center text-sm text-muted-foreground">
                  아직 응시한 학생이 없습니다.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

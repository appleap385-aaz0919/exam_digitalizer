'use client';

import { useQuery } from '@tanstack/react-query';
import { batchApi, examApi, classroomApi, questionApi, adminApi } from '@/lib/api';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Upload, Map, FileText, ClipboardList, School,
  BarChart3, ArrowRight, Clock, Users, AlertCircle,
} from 'lucide-react';

export default function TeacherDashboard() {
  const batches = useQuery({ queryKey: ['batches'], queryFn: () => batchApi.list() });
  const exams = useQuery({ queryKey: ['exams'], queryFn: () => examApi.list({}) });
  const classrooms = useQuery({ queryKey: ['classrooms'], queryFn: () => classroomApi.list() });
  const questions = useQuery({ queryKey: ['questions'], queryFn: () => questionApi.list({ limit: 1 }) });
  const humanReview = useQuery({
    queryKey: ['humanReviewCount'],
    queryFn: async () => {
      try {
        const res = await adminApi.listHumanReview();
        return res.data?.total ?? 0;
      } catch { return 0; }
    },
    refetchInterval: 60_000,
  });

  const batchList: any[] = batches.data?.data.data ?? [];
  const examList: any[] = exams.data?.data.data ?? [];
  const classroomList: any[] = classrooms.data?.data.data ?? [];
  const pendingReview = humanReview.data ?? 0;

  const stats = [
    { label: '업로드 배치', value: batches.data?.data.meta?.total ?? batchList.length, icon: Upload, href: '/teacher/batches', color: 'text-blue-600', bg: 'bg-blue-50 dark:bg-blue-950/40', ring: 'ring-blue-100' },
    { label: '제작된 문항', value: questions.data?.data.meta?.total ?? 0, icon: FileText, href: '/teacher/learning-maps', color: 'text-emerald-600', bg: 'bg-emerald-50 dark:bg-emerald-950/40', ring: 'ring-emerald-100' },
    { label: '시험지', value: exams.data?.data.meta?.total ?? examList.length, icon: ClipboardList, href: '/teacher/exams', color: 'text-violet-600', bg: 'bg-violet-50 dark:bg-violet-950/40', ring: 'ring-violet-100' },
    { label: '학급', value: classroomList.length, icon: School, href: '/teacher/classrooms', color: 'text-amber-600', bg: 'bg-amber-50 dark:bg-amber-950/40', ring: 'ring-amber-100' },
  ];

  const recentBatches = batchList.slice(0, 3);
  const recentExams = examList.slice(0, 3);

  return (
    <div className="space-y-8">
      {/* 헤더 */}
      <div>
        <h1 className="text-2xl font-bold">대시보드</h1>
        <p className="text-muted-foreground text-sm mt-1 leading-relaxed">시험 문항 디지털라이징 현황을 한눈에 확인하세요</p>
      </div>

      {/* 검토 대기 알림 배너 */}
      {pendingReview > 0 && (
        <Link href="/teacher/human-review">
          <div className="flex items-center gap-3 p-4 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200/60 dark:border-amber-800/40 hover:border-amber-300 transition-colors group cursor-pointer">
            <div className="w-10 h-10 rounded-lg bg-amber-100 dark:bg-amber-900/50 flex items-center justify-center shrink-0">
              <AlertCircle className="w-5 h-5 text-amber-600" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">검토가 필요한 문항이 {pendingReview}개 있습니다</p>
              <p className="text-xs text-amber-600/70 dark:text-amber-400/70 mt-0.5">AI가 3회 반려한 문항을 직접 확인해 주세요</p>
            </div>
            <ArrowRight className="w-4 h-4 text-amber-400 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </Link>
      )}

      {/* 통계 카드 */}
      <div className="grid grid-cols-4 gap-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <Link key={s.label} href={s.href}>
              <Card className="card-hover cursor-pointer border-transparent hover:border-border/50">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-[13px] text-muted-foreground font-medium">{s.label}</p>
                      <p className="text-3xl font-bold mt-1.5 tabular-nums">{s.value}</p>
                    </div>
                    <div className={`w-11 h-11 rounded-xl flex items-center justify-center ${s.bg} ring-1 ${s.ring}`}>
                      <Icon className={`w-5 h-5 ${s.color}`} />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <div className="grid grid-cols-2 gap-5">
        {/* 최근 배치 현황 */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-[15px]">최근 업로드</CardTitle>
                <CardDescription className="text-xs mt-0.5">HWP 파싱 진행 현황</CardDescription>
              </div>
              <Link href="/teacher/batches">
                <Button variant="ghost" size="sm" className="text-xs text-muted-foreground hover:text-foreground h-8">
                  전체 보기 <ArrowRight className="w-3 h-3 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="space-y-1 pt-0">
            {recentBatches.length > 0 ? recentBatches.map((b: any) => (
              <Link key={b.id} href="/teacher/batches"
                className="flex items-center justify-between p-3 rounded-lg hover:bg-accent/60 transition-colors">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-mono font-medium truncate">{b.id}</div>
                  <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                    <span>{b.total_questions ?? 0}문항</span>
                    {b.created_at && (
                      <>
                        <span className="text-muted-foreground/30">·</span>
                        <Clock className="w-3 h-3 opacity-50" />
                        <span>{new Date(b.created_at).toLocaleDateString('ko-KR')}</span>
                      </>
                    )}
                  </div>
                </div>
                <Badge variant={
                  b.status === 'COMPLETED' ? 'default' :
                  b.status === 'PARSING' ? 'secondary' : 'outline'
                } className="text-[10px] shrink-0">
                  {b.status}
                </Badge>
              </Link>
            )) : (
              <div className="text-sm text-muted-foreground text-center py-8">
                <Upload className="w-8 h-8 mx-auto mb-2 opacity-20" />
                아직 업로드한 배치가 없습니다
              </div>
            )}
          </CardContent>
        </Card>

        {/* 최근 시험 현황 */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-[15px]">최근 시험지</CardTitle>
                <CardDescription className="text-xs mt-0.5">시험지 구성 현황</CardDescription>
              </div>
              <Link href="/teacher/exams">
                <Button variant="ghost" size="sm" className="text-xs text-muted-foreground hover:text-foreground h-8">
                  전체 보기 <ArrowRight className="w-3 h-3 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="space-y-1 pt-0">
            {recentExams.length > 0 ? recentExams.map((e: any) => (
              <Link key={e.id} href="/teacher/exams"
                className="flex items-center justify-between p-3 rounded-lg hover:bg-accent/60 transition-colors">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{e.title || e.id}</div>
                  <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                    <span>{e.question_count ?? 0}문항</span>
                    <span className="text-muted-foreground/30">·</span>
                    <span>{e.total_points ?? 0}점</span>
                  </div>
                </div>
                <Badge variant={
                  e.status === 'CONFIRMED' ? 'default' :
                  e.status === 'DRAFT' ? 'secondary' : 'outline'
                } className="text-[10px] shrink-0">
                  {e.status}
                </Badge>
              </Link>
            )) : (
              <div className="text-sm text-muted-foreground text-center py-8">
                <ClipboardList className="w-8 h-8 mx-auto mb-2 opacity-20" />
                아직 만든 시험지가 없습니다
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 학급 현황 + 빠른 시작 */}
      <div className="grid grid-cols-2 gap-5">
        {/* 학급 현황 */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-[15px]">학급 현황</CardTitle>
                <CardDescription className="text-xs mt-0.5">학급별 학생 및 시험 배포</CardDescription>
              </div>
              <Link href="/teacher/classrooms">
                <Button variant="ghost" size="sm" className="text-xs text-muted-foreground hover:text-foreground h-8">
                  전체 보기 <ArrowRight className="w-3 h-3 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="space-y-1 pt-0">
            {classroomList.length > 0 ? classroomList.slice(0, 4).map((c: any) => (
              <Link key={c.id} href="/teacher/classrooms"
                className="flex items-center justify-between p-3 rounded-lg hover:bg-accent/60 transition-colors">
                <div>
                  <div className="text-sm font-medium">{c.name}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{c.grade}학년 · {c.subject}</div>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Users className="w-3 h-3 opacity-50" />
                    {c.student_count ?? 0}명
                  </span>
                  <span className="flex items-center gap-1">
                    <ClipboardList className="w-3 h-3 opacity-50" />
                    {c.exam_count ?? 0}시험
                  </span>
                </div>
              </Link>
            )) : (
              <div className="text-sm text-muted-foreground text-center py-8">
                <School className="w-8 h-8 mx-auto mb-2 opacity-20" />
                아직 생성한 학급이 없습니다
              </div>
            )}
          </CardContent>
        </Card>

        {/* 빠른 시작 */}
        <Card className="border-0 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-[15px]">빠른 시작</CardTitle>
            <CardDescription className="text-xs mt-0.5">자주 사용하는 기능</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2.5 pt-0">
            <Link href="/teacher/batches">
              <Button variant="outline" className="w-full justify-start h-auto py-3.5 px-4 hover:bg-blue-50/50 dark:hover:bg-blue-950/20 hover:border-blue-200 transition-colors">
                <div className="w-9 h-9 rounded-lg bg-blue-50 dark:bg-blue-950/40 flex items-center justify-center mr-3 shrink-0">
                  <Upload className="w-4.5 h-4.5 text-blue-600" />
                </div>
                <div className="text-left">
                  <div className="font-medium text-sm">HWP 파일 업로드</div>
                  <div className="text-xs text-muted-foreground mt-0.5">시험지를 올리면 AI가 자동으로 문항을 추출합니다</div>
                </div>
              </Button>
            </Link>
            <Link href="/teacher/learning-maps">
              <Button variant="outline" className="w-full justify-start h-auto py-3.5 px-4 hover:bg-emerald-50/50 dark:hover:bg-emerald-950/20 hover:border-emerald-200 transition-colors">
                <div className="w-9 h-9 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 flex items-center justify-center mr-3 shrink-0">
                  <Map className="w-4.5 h-4.5 text-emerald-600" />
                </div>
                <div className="text-left">
                  <div className="font-medium text-sm">학습맵에서 문항 탐색</div>
                  <div className="text-xs text-muted-foreground mt-0.5">교과과정 트리에서 단원별 문항을 찾아보세요</div>
                </div>
              </Button>
            </Link>
            <Link href="/teacher/exams">
              <Button variant="outline" className="w-full justify-start h-auto py-3.5 px-4 hover:bg-violet-50/50 dark:hover:bg-violet-950/20 hover:border-violet-200 transition-colors">
                <div className="w-9 h-9 rounded-lg bg-violet-50 dark:bg-violet-950/40 flex items-center justify-center mr-3 shrink-0">
                  <ClipboardList className="w-4.5 h-4.5 text-violet-600" />
                </div>
                <div className="text-left">
                  <div className="font-medium text-sm">시험지 만들기</div>
                  <div className="text-xs text-muted-foreground mt-0.5">문항을 골라 시험지를 구성하고 학급에 배포하세요</div>
                </div>
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

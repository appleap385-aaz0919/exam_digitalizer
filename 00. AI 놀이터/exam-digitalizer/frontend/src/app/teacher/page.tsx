'use client';

import { useQuery } from '@tanstack/react-query';
import { batchApi, examApi, classroomApi, questionApi } from '@/lib/api';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Upload, Map, FileText, ClipboardList, School,
  BarChart3, ArrowRight, Clock, Users, CheckCircle2,
} from 'lucide-react';

export default function TeacherDashboard() {
  const batches = useQuery({ queryKey: ['batches'], queryFn: () => batchApi.list() });
  const exams = useQuery({ queryKey: ['exams'], queryFn: () => examApi.list({}) });
  const classrooms = useQuery({ queryKey: ['classrooms'], queryFn: () => classroomApi.list() });
  const questions = useQuery({ queryKey: ['questions'], queryFn: () => questionApi.list({ limit: 1 }) });

  const batchList: any[] = batches.data?.data.data ?? [];
  const examList: any[] = exams.data?.data.data ?? [];
  const classroomList: any[] = classrooms.data?.data.data ?? [];

  const stats = [
    { label: '업로드 배치', value: batches.data?.data.meta?.total ?? batchList.length, icon: Upload, href: '/teacher/batches', color: 'text-blue-600 bg-blue-50' },
    { label: '제작된 문항', value: questions.data?.data.meta?.total ?? 0, icon: FileText, href: '/teacher/learning-maps', color: 'text-emerald-600 bg-emerald-50' },
    { label: '시험지', value: exams.data?.data.meta?.total ?? examList.length, icon: ClipboardList, href: '/teacher/exams', color: 'text-violet-600 bg-violet-50' },
    { label: '학급', value: classroomList.length, icon: School, href: '/teacher/classrooms', color: 'text-amber-600 bg-amber-50' },
  ];

  // 최근 배치 3개
  const recentBatches = batchList.slice(0, 3);
  // 최근 시험 3개
  const recentExams = examList.slice(0, 3);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">대시보드</h1>
        <p className="text-muted-foreground text-sm mt-1">시험 문항 디지털라이징 현황</p>
      </div>

      {/* 통계 카드 */}
      <div className="grid grid-cols-4 gap-4">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <Link key={s.label} href={s.href}>
              <Card className="hover:shadow-md transition-shadow cursor-pointer">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm text-muted-foreground">{s.label}</p>
                      <p className="text-3xl font-bold mt-1">{s.value}</p>
                    </div>
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${s.color}`}>
                      <Icon className="w-5 h-5" />
                    </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          );
        })}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* 최근 배치 현황 */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">최근 업로드</CardTitle>
                <CardDescription>HWP 파싱 진행 현황</CardDescription>
              </div>
              <Link href="/teacher/batches">
                <Button variant="ghost" size="sm" className="text-xs">
                  전체 보기 <ArrowRight className="w-3 h-3 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {recentBatches.length > 0 ? recentBatches.map((b: any) => (
              <Link key={b.id} href="/teacher/batches"
                className="flex items-center justify-between p-3 rounded-lg hover:bg-accent transition-colors group">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-mono font-medium truncate">{b.id}</div>
                  <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                    <span>{b.total_questions ?? 0}문항</span>
                    {b.created_at && (
                      <>
                        <span>·</span>
                        <Clock className="w-3 h-3" />
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
              <div className="text-sm text-muted-foreground text-center py-6">
                아직 업로드한 배치가 없습니다
              </div>
            )}
          </CardContent>
        </Card>

        {/* 최근 시험 현황 */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">최근 시험지</CardTitle>
                <CardDescription>시험지 구성 현황</CardDescription>
              </div>
              <Link href="/teacher/exams">
                <Button variant="ghost" size="sm" className="text-xs">
                  전체 보기 <ArrowRight className="w-3 h-3 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {recentExams.length > 0 ? recentExams.map((e: any) => (
              <Link key={e.id} href="/teacher/exams"
                className="flex items-center justify-between p-3 rounded-lg hover:bg-accent transition-colors group">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{e.title || e.id}</div>
                  <div className="text-xs text-muted-foreground mt-0.5 flex items-center gap-2">
                    <span>{e.question_count ?? 0}문항</span>
                    <span>·</span>
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
              <div className="text-sm text-muted-foreground text-center py-6">
                아직 만든 시험지가 없습니다
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* 학급 현황 + 빠른 시작 */}
      <div className="grid grid-cols-2 gap-4">
        {/* 학급 현황 */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">학급 현황</CardTitle>
                <CardDescription>학급별 학생 및 시험 배포</CardDescription>
              </div>
              <Link href="/teacher/classrooms">
                <Button variant="ghost" size="sm" className="text-xs">
                  전체 보기 <ArrowRight className="w-3 h-3 ml-1" />
                </Button>
              </Link>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {classroomList.length > 0 ? classroomList.slice(0, 4).map((c: any) => (
              <Link key={c.id} href="/teacher/classrooms"
                className="flex items-center justify-between p-3 rounded-lg hover:bg-accent transition-colors">
                <div>
                  <div className="text-sm font-medium">{c.name}</div>
                  <div className="text-xs text-muted-foreground mt-0.5">{c.grade}학년 · {c.subject}</div>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span className="flex items-center gap-1">
                    <Users className="w-3 h-3" />
                    {c.student_count ?? 0}명
                  </span>
                  <span className="flex items-center gap-1">
                    <ClipboardList className="w-3 h-3" />
                    {c.exam_count ?? 0}시험
                  </span>
                </div>
              </Link>
            )) : (
              <div className="text-sm text-muted-foreground text-center py-6">
                아직 생성한 학급이 없습니다
              </div>
            )}
          </CardContent>
        </Card>

        {/* 빠른 시작 */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">빠른 시작</CardTitle>
            <CardDescription>자주 사용하는 기능</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Link href="/teacher/batches">
              <Button variant="outline" className="w-full justify-start h-auto py-4">
                <Upload className="w-5 h-5 mr-3 text-blue-600" />
                <div className="text-left">
                  <div className="font-medium">HWP 파일 업로드</div>
                  <div className="text-xs text-muted-foreground">시험지를 올리면 AI가 자동으로 문항을 추출합니다</div>
                </div>
              </Button>
            </Link>
            <Link href="/teacher/learning-maps">
              <Button variant="outline" className="w-full justify-start h-auto py-4">
                <Map className="w-5 h-5 mr-3 text-emerald-600" />
                <div className="text-left">
                  <div className="font-medium">학습맵에서 문항 탐색</div>
                  <div className="text-xs text-muted-foreground">교과과정 트리에서 단원별 문항을 찾아보세요</div>
                </div>
              </Button>
            </Link>
            <Link href="/teacher/exams">
              <Button variant="outline" className="w-full justify-start h-auto py-4">
                <ClipboardList className="w-5 h-5 mr-3 text-violet-600" />
                <div className="text-left">
                  <div className="font-medium">시험지 만들기</div>
                  <div className="text-xs text-muted-foreground">문항을 골라 시험지를 구성하고 학급에 배포하세요</div>
                </div>
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

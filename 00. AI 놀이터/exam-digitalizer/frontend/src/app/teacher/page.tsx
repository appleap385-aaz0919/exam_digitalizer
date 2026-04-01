'use client';

import { useQuery } from '@tanstack/react-query';
import { batchApi, examApi, classroomApi, questionApi } from '@/lib/api';
import Link from 'next/link';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Upload, Map, FileText, ClipboardList, School, BarChart3, ArrowRight } from 'lucide-react';

export default function TeacherDashboard() {
  const batches = useQuery({ queryKey: ['batches'], queryFn: () => batchApi.list() });
  const exams = useQuery({ queryKey: ['exams'], queryFn: () => examApi.list({}) });
  const classrooms = useQuery({ queryKey: ['classrooms'], queryFn: () => classroomApi.list() });
  const questions = useQuery({ queryKey: ['questions'], queryFn: () => questionApi.list({ limit: 1 }) });

  const stats = [
    { label: '업로드 배치', value: batches.data?.data.meta?.total ?? 0, icon: Upload, href: '/teacher/batches', color: 'text-blue-600 bg-blue-50' },
    { label: '제작된 문항', value: questions.data?.data.meta?.total ?? 0, icon: FileText, href: '/teacher/questions', color: 'text-emerald-600 bg-emerald-50' },
    { label: '시험지', value: exams.data?.data.meta?.total ?? 0, icon: ClipboardList, href: '/teacher/exams', color: 'text-violet-600 bg-violet-50' },
    { label: '학급', value: classrooms.data?.data.data?.length ?? 0, icon: School, href: '/teacher/classrooms', color: 'text-amber-600 bg-amber-50' },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">대시보드</h1>
        <p className="text-muted-foreground text-sm mt-1">시험 문항 디지털라이징 현황</p>
      </div>

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
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">교사 워크플로우</CardTitle>
            <CardDescription>HWP 업로드부터 성적 조회까지</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {[
              { step: '1', label: 'HWP 시험지 업로드', desc: '파일을 올리면 AI가 자동 파싱', href: '/teacher/batches', icon: Upload },
              { step: '2', label: '문항 확인 및 탐색', desc: '파싱 결과 검토, 학습맵에서 탐색', href: '/teacher/questions', icon: FileText },
              { step: '3', label: '시험지 구성', desc: '문항 선택 → 배점 설정 → 확정', href: '/teacher/exams', icon: ClipboardList },
              { step: '4', label: '학급에 배포', desc: '학급 생성, 학생 등록, 시험 배포', href: '/teacher/classrooms', icon: School },
              { step: '5', label: '성적 확인', desc: '학생별 점수, 정답률 대시보드', href: '/teacher/grades', icon: BarChart3 },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <Link key={item.step} href={item.href}
                  className="flex items-center gap-3 p-3 rounded-lg hover:bg-accent transition-colors group">
                  <div className="w-7 h-7 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-bold shrink-0">
                    {item.step}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium">{item.label}</div>
                    <div className="text-xs text-muted-foreground">{item.desc}</div>
                  </div>
                  <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                </Link>
              );
            })}
          </CardContent>
        </Card>

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

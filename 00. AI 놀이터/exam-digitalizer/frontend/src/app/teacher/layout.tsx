'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import {
  LayoutDashboard,
  Map,
  Upload,
  ClipboardList,
  School,
  BarChart3,
  LogOut,
  BookOpen,
  AlertCircle,
  ChevronLeft,
} from 'lucide-react';
import { adminApi } from '@/lib/api';
import { useState } from 'react';

const NAV_ITEMS = [
  { href: '/teacher', label: '대시보드', icon: LayoutDashboard, exact: true },
  { href: '/teacher/learning-maps', label: '학습맵', icon: Map },
  { href: '/teacher/batches', label: 'HWP 업로드', icon: Upload },
  { href: '/teacher/human-review', label: '검토 대기', icon: AlertCircle, badge: true },
  { href: '/teacher/exams', label: '시험지 관리', icon: ClipboardList },
  { href: '/teacher/classrooms', label: '학급 관리', icon: School },
  { href: '/teacher/grades', label: '성적 조회', icon: BarChart3 },
];

export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  // 검토 대기 건수 조회
  const reviewCount = useQuery({
    queryKey: ['humanReviewCount'],
    queryFn: async () => {
      try {
        const res = await adminApi.listHumanReview();
        return res.data?.total ?? 0;
      } catch {
        return 0;
      }
    },
    refetchInterval: 60_000,
  });

  const pendingCount = reviewCount.data ?? 0;

  return (
    <div className="flex min-h-screen">
      <aside
        className={`${collapsed ? 'w-16' : 'w-60'} bg-sidebar text-sidebar-foreground flex flex-col transition-all duration-200 ease-in-out relative`}
        role="navigation"
        aria-label="메인 메뉴"
      >
        {/* 로고 */}
        <div className={`p-5 ${collapsed ? 'px-3' : ''}`}>
          <Link href="/teacher" className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-400 flex items-center justify-center shrink-0 shadow-lg shadow-emerald-500/20">
              <BookOpen className="w-4.5 h-4.5 text-white" />
            </div>
            {!collapsed && (
              <div>
                <h2 className="text-sm font-bold tracking-tight">출제 마법사</h2>
                <p className="text-[10px] text-sidebar-foreground/40 font-medium">Exam Digitalizer</p>
              </div>
            )}
          </Link>
        </div>

        <Separator className="bg-sidebar-border/50" />

        {/* 네비게이션 */}
        <nav className="flex-1 py-4 px-2.5 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = item.exact
              ? pathname === item.href
              : pathname === item.href || pathname.startsWith(item.href + '/');
            const showBadge = item.badge && pendingCount > 0;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-[13px] transition-all duration-150 group relative ${
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground font-semibold shadow-sm'
                    : 'text-sidebar-foreground/60 hover:bg-sidebar-accent/40 hover:text-sidebar-accent-foreground'
                }`}
                title={collapsed ? item.label : undefined}
              >
                <Icon className={`w-[18px] h-[18px] shrink-0 transition-colors ${
                  isActive ? 'text-sidebar-primary' : 'group-hover:text-sidebar-foreground/80'
                }`} />
                {!collapsed && (
                  <>
                    <span>{item.label}</span>
                    {showBadge && (
                      <Badge
                        variant="destructive"
                        className="ml-auto text-[10px] px-1.5 py-0 h-[18px] min-w-[18px] flex items-center justify-center font-bold animate-pulse"
                      >
                        {pendingCount}
                      </Badge>
                    )}
                  </>
                )}
                {collapsed && showBadge && (
                  <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-destructive rounded-full border-2 border-sidebar" />
                )}
                {/* 액티브 인디케이터 */}
                {isActive && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 bg-sidebar-primary rounded-r-full" />
                )}
              </Link>
            );
          })}
        </nav>

        <Separator className="bg-sidebar-border/50" />

        {/* 하단 */}
        <div className="p-2.5 space-y-1">
          {/* 축소/확장 토글 */}
          <Button
            variant="ghost"
            size="sm"
            className={`w-full text-sidebar-foreground/40 hover:text-sidebar-foreground/70 hover:bg-sidebar-accent/30 ${collapsed ? 'justify-center' : 'justify-start'}`}
            onClick={() => setCollapsed(!collapsed)}
          >
            <ChevronLeft className={`w-4 h-4 transition-transform duration-200 ${collapsed ? 'rotate-180' : ''} ${collapsed ? '' : 'mr-2'}`} />
            {!collapsed && <span className="text-xs">사이드바 접기</span>}
          </Button>
          {/* 로그아웃 */}
          <Button
            variant="ghost"
            size="sm"
            className={`w-full text-sidebar-foreground/40 hover:text-destructive hover:bg-destructive/10 ${collapsed ? 'justify-center' : 'justify-start'}`}
            onClick={() => {
              localStorage.removeItem('access_token');
              window.location.href = '/';
            }}
          >
            <LogOut className={`w-4 h-4 ${collapsed ? '' : 'mr-2'}`} />
            {!collapsed && <span className="text-xs">로그아웃</span>}
          </Button>
        </div>
      </aside>

      <main className="flex-1 p-8 overflow-auto" role="main" aria-label="콘텐츠 영역">
        <div className="max-w-7xl mx-auto">
          {children}
        </div>
      </main>
    </div>
  );
}

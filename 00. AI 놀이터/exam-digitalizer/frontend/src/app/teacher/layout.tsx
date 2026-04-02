'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import {
  LayoutDashboard,
  Map,
  Upload,
  ClipboardList,
  School,
  BarChart3,
  LogOut,
  BookOpen,
} from 'lucide-react';

const NAV_ITEMS = [
  { href: '/teacher', label: '대시보드', icon: LayoutDashboard },
  { href: '/teacher/learning-maps', label: '학습맵', icon: Map },
  { href: '/teacher/batches', label: 'HWP 업로드', icon: Upload },
  { href: '/teacher/exams', label: '시험지 관리', icon: ClipboardList },
  { href: '/teacher/classrooms', label: '학급 관리', icon: School },
  { href: '/teacher/grades', label: '성적 조회', icon: BarChart3 },
];

export default function TeacherLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="flex min-h-screen">
      <aside className="w-60 bg-sidebar text-sidebar-foreground flex flex-col" role="navigation" aria-label="메인 메뉴">
        <div className="p-5">
          <Link href="/teacher" className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-sidebar-primary flex items-center justify-center">
              <BookOpen className="w-4 h-4 text-sidebar-primary-foreground" />
            </div>
            <div>
              <h2 className="text-sm font-bold">출제 마법사</h2>
              <p className="text-[10px] text-sidebar-foreground/50">Exam Digitalizer</p>
            </div>
          </Link>
        </div>
        <Separator className="bg-sidebar-border" />
        <nav className="flex-1 py-3 px-3 space-y-0.5">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href ||
              (item.href !== '/teacher' && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground font-medium'
                    : 'text-sidebar-foreground/70 hover:bg-sidebar-accent/50 hover:text-sidebar-accent-foreground'
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <Separator className="bg-sidebar-border" />
        <div className="p-3">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start text-sidebar-foreground/50 hover:text-destructive hover:bg-destructive/10"
            onClick={() => {
              localStorage.removeItem('access_token');
              window.location.href = '/';
            }}
          >
            <LogOut className="w-4 h-4 mr-2" />
            로그아웃
          </Button>
        </div>
      </aside>

      <main className="flex-1 p-6 overflow-auto" role="main" aria-label="콘텐츠 영역">
        {children}
      </main>
    </div>
  );
}

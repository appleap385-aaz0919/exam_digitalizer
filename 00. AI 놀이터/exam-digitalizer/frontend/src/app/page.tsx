'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { authApi } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { BookOpen, GraduationCap, Lock, Mail } from 'lucide-react';

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await authApi.login(email, password);
      localStorage.setItem('access_token', res.data.access_token);
      localStorage.setItem('refresh_token', res.data.refresh_token);
      router.push('/teacher');
    } catch {
      setError('이메일 또는 비밀번호를 확인해주세요');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-dvh bg-gradient-to-br from-slate-50 via-teal-50/20 to-emerald-50/30 relative overflow-hidden">
      {/* 배경 장식 */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/4 -left-32 w-96 h-96 bg-teal-100/30 rounded-full blur-3xl" />
        <div className="absolute bottom-1/4 -right-32 w-96 h-96 bg-emerald-100/30 rounded-full blur-3xl" />
      </div>

      <div className="w-full max-w-[420px] px-4 relative z-10">
        {/* 로고 영역 */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-500 shadow-lg shadow-emerald-500/25 mb-4">
            <BookOpen className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold">출제 마법사</h1>
          <p className="text-sm text-muted-foreground mt-1.5 leading-relaxed">AI 기반 시험 문항 디지털라이징 시스템</p>
        </div>

        {/* 로그인 카드 */}
        <Card className="border-0 shadow-xl shadow-black/[0.04] backdrop-blur-sm">
          <CardContent className="p-6 pt-6">
            <form onSubmit={handleLogin} className="space-y-4">
              <div className="space-y-1.5">
                <label className="text-[13px] font-medium text-foreground/80">이메일</label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/40" />
                  <Input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="teacher01@test.com"
                    className="pl-10 h-11"
                    required
                  />
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="text-[13px] font-medium text-foreground/80">비밀번호</label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground/40" />
                  <Input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="비밀번호를 입력하세요"
                    className="pl-10 h-11"
                    required
                  />
                </div>
              </div>

              {error && (
                <div className="p-3 bg-destructive/8 text-destructive text-sm rounded-lg border border-destructive/15 flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-destructive shrink-0" />
                  {error}
                </div>
              )}

              <Button
                type="submit"
                disabled={loading}
                className="w-full h-11 text-[15px] font-semibold shadow-sm hover:shadow-md transition-all"
              >
                {loading ? '로그인 중...' : '로그인'}
              </Button>
            </form>

            <div className="mt-6 pt-5 border-t border-border/50">
              <a
                href="/student"
                className="flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm text-muted-foreground hover:text-primary hover:bg-primary/5 transition-all"
              >
                <GraduationCap className="w-4 h-4" />
                학생으로 시험 응시하기
              </a>
            </div>
          </CardContent>
        </Card>

        {/* 하단 정보 */}
        <p className="text-center text-[11px] text-muted-foreground/50 mt-6">
          시험 문항 디지털라이징 시스템 v1.0
        </p>
      </div>
    </div>
  );
}

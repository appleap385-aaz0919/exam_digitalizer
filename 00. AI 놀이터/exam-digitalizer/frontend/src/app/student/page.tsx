'use client';

import { useState, useEffect, useRef } from 'react';
import { studentApi } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  GraduationCap, ChevronLeft, ChevronRight,
  BookOpen, CheckCircle, AlertTriangle, Clock,
} from 'lucide-react';

interface ExamQuestion {
  pkey: string;
  seq_order: number;
  points: number;
  render_html: string | null;
  raw_text: string | null;
  question_type: string | null;
}

interface Answer {
  pkey: string;
  seq: number;
  value: string;
}

type SelectMode = 'list' | 'manual';

export default function StudentPage() {
  const [step, setStep] = useState<'code' | 'select' | 'exams' | 'cbt' | 'confirm' | 'result'>('code');
  const [inviteCode, setInviteCode] = useState('');

  // QR코드에서 진입 시 초대코드 자동 입력 + 자동 접속
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    if (code && step === 'code' && !classroom) {
      setInviteCode(code);
      (async () => {
        try {
          const res = await studentApi.findClassroom(code);
          setClassroom(res.data);
          setStudents(res.data.students ?? []);
          setStep('select');
        } catch { /* 실패 시 수동 입력 */ }
      })();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  const [classroom, setClassroom] = useState<any>(null);
  const [students, setStudents] = useState<any[]>([]);
  const [selectedStudent, setSelectedStudent] = useState<any>(null);
  const [studentToken, setStudentToken] = useState('');
  const [examList, setExamList] = useState<any[]>([]);
  const [currentExam, setCurrentExam] = useState<any>(null);
  const [examQuestions, setExamQuestions] = useState<ExamQuestion[]>([]);
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [currentQ, setCurrentQ] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [selectMode, setSelectMode] = useState<SelectMode>('list');
  const [manualName, setManualName] = useState('');
  const [manualNumber, setManualNumber] = useState<number | ''>('');
  const [submitted, setSubmitted] = useState(false);
  const [submissionId, setSubmissionId] = useState<number | null>(null);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // ── helpers ──────────────────────────────────────────────
  const loadExams = async (classroomId: string) => {
    try {
      const res = await studentApi.getExams(classroomId);
      setExamList(res.data.data ?? []);
    } catch {
      setExamList([]);
    }
  };

  const handleCodeSubmit = async () => {
    if (!inviteCode.trim()) return;
    setError('');
    setLoading(true);
    try {
      const res = await studentApi.findClassroom(inviteCode.trim());
      setClassroom(res.data);
      setStudents(res.data.students ?? []);
      setStep('select');
    } catch {
      setError('올바른 초대 코드를 입력해주세요.');
    } finally {
      setLoading(false);
    }
  };

  const afterAuth = async (token: string, student: any) => {
    setStudentToken(token);
    setSelectedStudent(student);
    await loadExams(classroom.classroom_id);
    setStep('exams');
  };

  const handleStudentSelect = async (student: any) => {
    setError('');
    setLoading(true);
    try {
      const res = await studentApi.selectStudent(classroom.classroom_id, student.id);
      await afterAuth(res.data.student_token, student);
    } catch {
      setError('학생 선택에 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const handleManualJoin = async () => {
    if (!manualName.trim() || !manualNumber) return;
    setError('');
    setLoading(true);
    try {
      const res = await studentApi.joinByName(classroom.classroom_id, manualName.trim(), +manualNumber);
      await afterAuth(res.data.student_token, { name: res.data.student_name, id: res.data.student_id });
    } catch {
      setError('접속에 실패했습니다. 다시 시도해주세요.');
    } finally {
      setLoading(false);
    }
  };

  const startExam = async (exam: any) => {
    setLoading(true);
    setError('');
    try {
      const res = await studentApi.getExamQuestions(exam.exam_id);
      const qs: ExamQuestion[] = res.data.questions ?? [];
      setCurrentExam({ ...exam, ...res.data });
      setExamQuestions(qs);
      setAnswers(qs.map(q => ({ pkey: q.pkey, seq: q.seq_order, value: '' })));

      // 세션 시작 (DB에 Submission 생성)
      try {
        const sessionRes = await studentApi.startSession(exam.id, studentToken);
        setSubmissionId(sessionRes.data.submission_id);
      } catch {
        // 세션 생성 실패해도 CBT 자체는 진행 가능
      }
      setCurrentQ(0);
      setSubmitted(false);
      // 타이머 시작
      const minutes = res.data.time_limit_minutes ?? 50;
      setRemainingSeconds(minutes * 60);
      if (timerRef.current) clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setRemainingSeconds(prev => {
          if (prev <= 1) {
            if (timerRef.current) clearInterval(timerRef.current);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
      setStep('cbt');
    } catch {
      setError('시험 정보를 불러오는 데 실패했습니다.');
    } finally {
      setLoading(false);
    }
  };

  const updateAnswer = (value: string) => {
    setAnswers(prev => prev.map((a, i) => i === currentQ ? { ...a, value } : a));
  };

  const handleSubmit = async () => {
    if (timerRef.current) clearInterval(timerRef.current);

    // 답안 DB 제출
    if (submissionId && studentToken) {
      try {
        await studentApi.submitSession(
          submissionId,
          studentToken,
          answers.map((a, i) => ({
            pkey: a.pkey,
            seq: a.seq,
            value: a.value,
            question_type: examQuestions[i]?.question_type || undefined,
          })),
        );
      } catch {
        // 제출 실패해도 결과 화면으로 이동 (오프라인 대비)
      }
    }

    setSubmitted(true);
    setStep('result');
  };

  // 시간 초과 시 자동 제출
  useEffect(() => {
    if (step === 'cbt' && remainingSeconds === 0 && !submitted) {
      handleSubmit();
    }
  }, [remainingSeconds, step, submitted]); // eslint-disable-line react-hooks/exhaustive-deps

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${String(sec).padStart(2, '0')}`;
  };

  // ── 초대 코드 입력 ───────────────────────────────────────
  if (step === 'code') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-emerald-50 via-blue-50 to-indigo-50">
        <Card className="w-full max-w-md shadow-xl border-0">
          <CardContent className="p-10">
            <div className="text-center mb-8">
              <div className="w-16 h-16 bg-gradient-to-br from-emerald-500 to-blue-600 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <GraduationCap className="w-8 h-8 text-white" />
              </div>
              <h1 className="text-2xl font-bold">시험 접속</h1>
              <p className="text-sm text-muted-foreground mt-1">선생님께 받은 초대 코드를 입력하세요</p>
            </div>
            <div className="space-y-4">
              <input
                value={inviteCode}
                onChange={e => setInviteCode(e.target.value.toUpperCase())}
                onKeyDown={e => e.key === 'Enter' && !loading && handleCodeSubmit()}
                placeholder="초대 코드 입력"
                maxLength={20}
                className="w-full text-center text-xl tracking-[0.3em] h-14 font-mono font-bold border rounded-xl px-4 bg-background focus:outline-none focus:ring-2 focus:ring-primary/30"
              />
              {error && <p className="text-sm text-destructive text-center">{error}</p>}
              <Button
                onClick={handleCodeSubmit}
                disabled={!inviteCode.trim() || loading}
                className="w-full h-12 text-base bg-gradient-to-r from-emerald-600 to-blue-600 hover:from-emerald-700 hover:to-blue-700"
              >
                {loading ? '확인 중...' : '접속하기'}
              </Button>
            </div>
            <div className="mt-6 text-center">
              <a href="/" className="text-xs text-muted-foreground hover:text-foreground transition-colors">
                교사 로그인
              </a>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── 이름 선택 / 직접 입력 ────────────────────────────────
  if (step === 'select') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-emerald-50 to-blue-50">
        <Card className="w-full max-w-md shadow-xl border-0">
          <CardContent className="p-8">
            <div className="text-center mb-5">
              <h2 className="text-xl font-bold">{classroom?.name}</h2>
              <p className="text-sm text-muted-foreground mt-0.5">{classroom?.grade}학년</p>
            </div>

            <div className="flex rounded-xl border overflow-hidden mb-5">
              <button
                onClick={() => setSelectMode('list')}
                className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                  selectMode === 'list' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:bg-accent'
                }`}
              >
                목록에서 선택
              </button>
              <button
                onClick={() => setSelectMode('manual')}
                className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                  selectMode === 'manual' ? 'bg-primary text-primary-foreground' : 'bg-card text-muted-foreground hover:bg-accent'
                }`}
              >
                이름 직접 입력
              </button>
            </div>

            {selectMode === 'list' && (
              <div className="space-y-1.5 max-h-64 overflow-y-auto">
                {students.map(s => (
                  <button
                    key={s.id}
                    onClick={() => !loading && handleStudentSelect(s)}
                    disabled={loading}
                    className="w-full px-4 py-3 border rounded-xl text-left hover:bg-emerald-50 hover:border-emerald-400 transition-colors flex items-center gap-3 disabled:opacity-50"
                  >
                    <span className="text-muted-foreground text-sm font-mono w-6">{String(s.student_number).padStart(2, '0')}</span>
                    <span className="font-medium">{s.name}</span>
                  </button>
                ))}
                {students.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-8">등록된 학생이 없습니다.</p>
                )}
              </div>
            )}

            {selectMode === 'manual' && (
              <div className="space-y-3">
                <div className="flex gap-2">
                  <div className="w-20">
                    <label className="text-xs text-muted-foreground mb-1 block">번호</label>
                    <Input
                      type="number"
                      value={manualNumber}
                      onChange={e => setManualNumber(e.target.value ? +e.target.value : '')}
                      min={1}
                      placeholder="번호"
                      className="h-12 text-center text-lg"
                      disabled={loading}
                    />
                  </div>
                  <div className="flex-1">
                    <label className="text-xs text-muted-foreground mb-1 block">이름</label>
                    <Input
                      value={manualName}
                      onChange={e => setManualName(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && !loading && manualName.trim() && manualNumber && handleManualJoin()}
                      placeholder="이름을 입력하세요"
                      className="h-12 text-center text-lg"
                      autoFocus
                      disabled={loading}
                    />
                  </div>
                </div>
                <Button onClick={handleManualJoin} disabled={!manualName.trim() || !manualNumber || loading} className="w-full h-11">
                  {loading ? '접속 중...' : '입장하기'}
                </Button>
              </div>
            )}

            {error && <p className="text-sm text-destructive text-center mt-3">{error}</p>}
            <button
              onClick={() => { setStep('code'); setError(''); setSelectMode('list'); setManualName(''); }}
              className="mt-4 w-full text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              뒤로
            </button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── 시험 목록 ────────────────────────────────────────────
  if (step === 'exams') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50">
        <Card className="w-full max-w-lg shadow-xl border-0">
          <CardContent className="p-8">
            <div className="text-center mb-6">
              <div className="w-12 h-12 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-3">
                <GraduationCap className="w-6 h-6 text-primary" />
              </div>
              <h2 className="text-xl font-bold">안녕하세요, {selectedStudent?.name}님!</h2>
              <p className="text-sm text-muted-foreground mt-1">{classroom?.name}</p>
            </div>

            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">배포된 시험</h3>
            <div className="space-y-2">
              {examList.map((ce: any) => (
                <button
                  key={ce.id}
                  onClick={() => !loading && startExam(ce)}
                  disabled={loading}
                  className="w-full p-4 border rounded-xl text-left hover:border-primary/50 hover:bg-primary/5 transition-colors group disabled:opacity-50"
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium">{ce.exam_title || ce.exam_id}</div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {ce.time_limit_minutes ?? '?'}분 · {ce.status}
                      </div>
                    </div>
                    <BookOpen className="w-5 h-5 text-muted-foreground/30 group-hover:text-primary transition-colors" />
                  </div>
                </button>
              ))}
              {examList.length === 0 && (
                <div className="p-8 text-center text-sm text-muted-foreground border rounded-xl">
                  현재 진행 가능한 시험이 없습니다.
                </div>
              )}
            </div>
            {error && <p className="text-sm text-destructive text-center mt-3">{error}</p>}
            {loading && <p className="text-sm text-muted-foreground text-center mt-3">시험을 불러오는 중...</p>}

            <button
              onClick={() => { setStep('code'); setSelectedStudent(null); setStudentToken(''); }}
              className="mt-6 w-full text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              다른 학급으로 접속
            </button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── CBT 응시 ─────────────────────────────────────────────
  if (step === 'cbt') {
    const q = examQuestions[currentQ];
    const answer = answers[currentQ];
    const total = examQuestions.length;
    const answeredCount = answers.filter(a => a.value.trim()).length;
    const allAnswered = answeredCount === total && total > 0;

    return (
      <div className="min-h-screen bg-muted/30">
        {/* 상단 바 */}
        <div className="bg-card border-b px-6 py-3 flex items-center justify-between sticky top-0 z-10 shadow-sm">
          <div>
            <div className="text-sm font-semibold">{currentExam?.title || '시험'}</div>
            <div className="text-xs text-muted-foreground">{selectedStudent?.name}</div>
          </div>
          <div className="flex items-center gap-2">
            <Badge
              variant={remainingSeconds < 300 ? 'destructive' : 'outline'}
              className="font-mono flex items-center gap-1"
            >
              <Clock className="w-3 h-3" />
              {formatTime(remainingSeconds)}
            </Badge>
            <Badge variant="outline" className="font-mono">
              {currentQ + 1} / {total}문항
            </Badge>
            <Badge
              variant={allAnswered ? 'default' : 'secondary'}
              className={allAnswered ? 'bg-emerald-600' : ''}
            >
              {answeredCount}/{total} 완료
            </Badge>
            <Button
              onClick={() => setStep('confirm')}
              size="sm"
              className="ml-2 bg-red-500 hover:bg-red-600 text-white"
            >
              답안 제출
            </Button>
          </div>
        </div>

        <div className="max-w-3xl mx-auto p-6">
          {/* 문항 번호 네비게이션 */}
          <div className="flex gap-1.5 mb-6 flex-wrap">
            {examQuestions.map((_, i) => (
              <button
                key={i}
                onClick={() => setCurrentQ(i)}
                className={`w-9 h-9 rounded-lg text-xs font-semibold transition-colors ${
                  i === currentQ
                    ? 'bg-primary text-primary-foreground shadow-sm'
                    : answers[i]?.value.trim()
                    ? 'bg-emerald-100 text-emerald-700 border border-emerald-300'
                    : 'bg-card border text-muted-foreground hover:bg-accent'
                }`}
              >
                {i + 1}
              </button>
            ))}
          </div>

          {/* 문항 카드 */}
          {q && (
            <Card className="mb-6 shadow-sm">
              <CardContent className="p-6">
                <div className="flex items-center gap-2 mb-5">
                  <span className="bg-primary text-primary-foreground text-sm px-3 py-1 rounded-full font-semibold">
                    {currentQ + 1}번
                  </span>
                  <span className="text-xs text-muted-foreground font-mono">{q.pkey}</span>
                  <Badge variant="outline" className="text-xs ml-auto">{q.points}점</Badge>
                </div>

                {/* 문항 내용 */}
                <div className="mb-6">
                  {q.render_html ? (
                    <div
                      className="p-4 bg-muted/40 rounded-xl text-sm leading-relaxed"
                      dangerouslySetInnerHTML={{ __html: q.render_html }}
                    />
                  ) : q.raw_text ? (
                    <div className="p-4 bg-muted/40 rounded-xl text-sm leading-relaxed whitespace-pre-wrap font-mono">
                      {q.raw_text}
                    </div>
                  ) : (
                    <div className="p-4 bg-muted/40 rounded-xl text-sm text-muted-foreground italic">
                      문항 내용을 불러오는 중...
                    </div>
                  )}
                </div>

                {/* 답안 입력 — 유형별 분기 */}
                <div>
                  <label className="text-sm font-medium text-muted-foreground block mb-2">답안 입력</label>

                  {q.question_type === '객관식' ? (
                    /* 객관식: 1~5번 라디오 버튼 */
                    <div className="grid grid-cols-5 gap-2">
                      {[1, 2, 3, 4, 5].map(n => (
                        <button
                          key={n}
                          onClick={() => updateAnswer(String(n))}
                          className={`py-3 rounded-xl text-sm font-semibold border-2 transition-all ${
                            answer?.value === String(n)
                              ? 'bg-primary text-primary-foreground border-primary shadow-md scale-105'
                              : 'bg-card border-muted-foreground/20 hover:border-primary/50 hover:bg-accent'
                          }`}
                        >
                          {n}
                        </button>
                      ))}
                    </div>
                  ) : q.question_type === '단답형' ? (
                    /* 단답형: 짧은 입력 */
                    <Input
                      value={answer?.value ?? ''}
                      onChange={e => updateAnswer(e.target.value)}
                      placeholder="답을 입력하세요"
                      className="h-12 text-base"
                      autoFocus
                    />
                  ) : (
                    /* 서술형 / 기타: 텍스트 영역 */
                    <textarea
                      value={answer?.value ?? ''}
                      onChange={e => updateAnswer(e.target.value)}
                      placeholder="답을 입력하세요"
                      rows={4}
                      className="w-full px-4 py-3 border rounded-xl text-sm resize-none bg-background focus:outline-none focus:ring-2 focus:ring-primary/30 transition"
                    />
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {total === 0 && (
            <Card>
              <CardContent className="p-12 text-center text-muted-foreground text-sm">
                이 시험에 등록된 문항이 없습니다.
              </CardContent>
            </Card>
          )}

          {/* 이전/다음 */}
          <div className="flex justify-between">
            <Button
              variant="outline"
              onClick={() => setCurrentQ(Math.max(0, currentQ - 1))}
              disabled={currentQ === 0}
            >
              <ChevronLeft className="w-4 h-4 mr-1" /> 이전
            </Button>
            {currentQ < total - 1 ? (
              <Button onClick={() => setCurrentQ(currentQ + 1)}>
                다음 <ChevronRight className="w-4 h-4 ml-1" />
              </Button>
            ) : (
              <Button
                onClick={() => setStep('confirm')}
                className="bg-red-500 hover:bg-red-600 text-white"
              >
                답안 제출 →
              </Button>
            )}
          </div>

          {/* 미답 안내 */}
          {!allAnswered && (
            <p className="mt-4 text-xs text-amber-600 text-center">
              미답 문항: {answers.filter(a => !a.value.trim()).map((_, i) => answers.findIndex((a2, i2) => i2 >= i && !a2.value.trim()) + 1).filter((v, i, arr) => arr.indexOf(v) === i).join(', ')}번
              ({total - answeredCount}문항 남음)
            </p>
          )}
        </div>
      </div>
    );
  }

  // ── 제출 확인 ─────────────────────────────────────────────
  if (step === 'confirm') {
    const answeredCount = answers.filter(a => a.value.trim()).length;
    const unansweredNums = answers
      .map((a, i) => (!a.value.trim() ? i + 1 : null))
      .filter(Boolean);

    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-amber-50 to-red-50">
        <Card className="w-full max-w-md shadow-xl border-0">
          <CardContent className="p-10 text-center">
            <div className={`w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5 ${
              unansweredNums.length > 0 ? 'bg-amber-100' : 'bg-emerald-100'
            }`}>
              {unansweredNums.length > 0
                ? <AlertTriangle className="w-7 h-7 text-amber-600" />
                : <CheckCircle className="w-7 h-7 text-emerald-600" />
              }
            </div>

            <h2 className="text-xl font-bold mb-2">답안을 제출하시겠습니까?</h2>
            <p className="text-sm text-muted-foreground mb-5">
              제출 후에는 수정이 불가능합니다.
            </p>

            <div className="bg-muted/50 rounded-xl p-4 text-sm mb-6 text-left space-y-1.5">
              <div className="flex justify-between">
                <span className="text-muted-foreground">전체 문항</span>
                <span className="font-semibold">{answers.length}문항</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">답안 입력 완료</span>
                <span className="font-semibold text-emerald-600">{answeredCount}문항</span>
              </div>
              {unansweredNums.length > 0 && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">미답 문항</span>
                  <span className="font-semibold text-amber-600">
                    {unansweredNums.join(', ')}번 ({unansweredNums.length}문항)
                  </span>
                </div>
              )}
            </div>

            <div className="flex gap-3">
              <Button variant="outline" className="flex-1" onClick={() => setStep('cbt')}>
                계속 풀기
              </Button>
              <Button
                className="flex-1 bg-red-500 hover:bg-red-600 text-white"
                onClick={handleSubmit}
              >
                최종 제출
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── 제출 완료 ─────────────────────────────────────────────
  if (step === 'result') {
    const answeredCount = answers.filter(a => a.value.trim()).length;
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-emerald-50 to-blue-50">
        <Card className="w-full max-w-md shadow-xl border-0">
          <CardContent className="p-10 text-center">
            <div className="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center mx-auto mb-5">
              <CheckCircle className="w-8 h-8 text-emerald-600" />
            </div>
            <h2 className="text-xl font-bold mb-2">답안이 제출되었습니다!</h2>
            <p className="text-muted-foreground text-sm mb-5">
              {answeredCount}/{answers.length}문항 응답 완료
            </p>
            <div className="bg-muted/50 rounded-xl p-4 text-sm text-muted-foreground mb-6">
              채점 결과는 선생님이 확인 후 알려드립니다.
            </div>
            <Button
              variant="outline"
              onClick={() => {
                setStep('code');
                setSelectedStudent(null);
                setStudentToken('');
                setAnswers([]);
                setExamQuestions([]);
                setManualName('');
                setSubmitted(false);
              }}
            >
              처음으로 돌아가기
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return null;
}

'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { classroomApi, examApi } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Plus, School, QrCode, Users, ClipboardCheck, Download, Pencil, Check, X, Trash2 } from 'lucide-react';

export default function ClassroomsPage() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [editingStudent, setEditingStudent] = useState<number | null>(null);
  const [editName, setEditName] = useState('');
  const [editNumber, setEditNumber] = useState(0);
  const [name, setName] = useState('');
  const [grade, setGrade] = useState('1');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [studentName, setStudentName] = useState('');
  const [studentNumber, setStudentNumber] = useState(1);
  const [showDeploy, setShowDeploy] = useState(false);
  const [deployExamId, setDeployExamId] = useState('');

  const classrooms = useQuery({ queryKey: ['classrooms'], queryFn: () => classroomApi.list() });
  const students = useQuery({
    queryKey: ['classStudents', selectedId],
    queryFn: () => classroomApi.listStudents(selectedId!),
    enabled: !!selectedId,
  });
  const classExams = useQuery({
    queryKey: ['classExams', selectedId],
    queryFn: () => classroomApi.listExams(selectedId!),
    enabled: !!selectedId,
  });
  // 모든 시험 가져오기 (limit 높임 — confirmed가 아닌 것도 표시, 상태 배지로 구분)
  const allExams = useQuery({
    queryKey: ['exams', 'all'],
    queryFn: () => examApi.list({ limit: 100 }),
  });

  const createMutation = useMutation({
    mutationFn: () => classroomApi.create({ name, grade: +grade }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['classrooms'] });
      setShowCreate(false);
      setName('');
    },
  });
  const addStudentMutation = useMutation({
    mutationFn: () => classroomApi.addStudent(selectedId!, studentName, studentNumber),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['classStudents', selectedId] });
      setStudentName('');
      setStudentNumber(prev => prev + 1);
    },
  });
  const updateStudentMutation = useMutation({
    mutationFn: ({ studentId, data }: { studentId: number; data: { name?: string; student_number?: number } }) =>
      classroomApi.updateStudent(selectedId!, studentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['classStudents', selectedId] });
      setEditingStudent(null);
    },
  });
  const deleteStudentMutation = useMutation({
    mutationFn: (studentId: number) => classroomApi.deleteStudent(selectedId!, studentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['classStudents', selectedId] });
      setEditingStudent(null);
    },
  });
  const deployMutation = useMutation({
    mutationFn: () => classroomApi.deployExam(selectedId!, { exam_id: deployExamId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['classExams', selectedId] });
      setShowDeploy(false);
      setDeployExamId('');
    },
  });

  const classList = classrooms.data?.data.data ?? [];
  const studentList = students.data?.data.data ?? [];
  const classExamList = classExams.data?.data.data ?? [];
  // 확정된 시험만 배포 가능, 나머지는 비활성화 표시
  const allExamList: any[] = allExams.data?.data.data ?? [];
  const selected = classList.find((c: any) => c.id === selectedId);

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">학급 관리</h1>
          <p className="text-muted-foreground text-sm mt-1">학급을 생성하고 학생을 등록한 뒤 시험을 배포하세요</p>
        </div>
        <Button onClick={() => setShowCreate(true)}>
          <Plus className="w-4 h-4 mr-2" />
          학급 생성
        </Button>
      </div>

      {/* 학급 생성 폼 */}
      {showCreate && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">새 학급 생성</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-3">
              <Input
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="학급명 (예: 1학년 3반)"
                className="flex-1"
              />
              <select value={grade} onChange={e => setGrade(e.target.value)}
                className="h-9 px-3 rounded-lg border bg-background text-sm">
                {[1, 2, 3, 4, 5, 6].map(g => (
                  <option key={g} value={String(g)}>{g}학년</option>
                ))}
              </select>
              <Button onClick={() => createMutation.mutate()} disabled={!name.trim()}>생성</Button>
              <Button variant="outline" onClick={() => setShowCreate(false)}>취소</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-3 gap-4">
        {/* 학급 목록 */}
        <Card className="max-h-[75vh] overflow-y-auto">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-muted-foreground flex items-center gap-2">
              <School className="w-4 h-4" /> 학급 목록
            </CardTitle>
          </CardHeader>
          <CardContent className="p-2">
            <div className="space-y-1">
              {classList.map((c: any) => (
                <button
                  key={c.id}
                  onClick={() => { setSelectedId(c.id); setShowDeploy(false); }}
                  className={`w-full text-left px-3 py-3 rounded-lg text-sm transition-colors ${
                    selectedId === c.id
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-accent'
                  }`}
                >
                  <div className="font-medium">{c.name}</div>
                  <div className={`text-xs mt-0.5 ${selectedId === c.id ? 'text-primary-foreground/70' : 'text-muted-foreground'}`}>
                    {c.grade}학년 · 코드: <span className="font-mono font-bold">{c.invite_code}</span>
                  </div>
                </button>
              ))}
              {classList.length === 0 && (
                <p className="text-xs text-muted-foreground py-6 text-center">학급이 없습니다</p>
              )}
            </div>
          </CardContent>
        </Card>

        {/* 학급 상세 */}
        <div className="col-span-2 space-y-4">
          {selected ? (
            <>
              {/* 초대 정보 */}
              <Card>
                <CardContent className="p-6">
                  <div className="flex items-start justify-between">
                    <div>
                      <h2 className="text-lg font-bold">{selected.name}</h2>
                      <p className="text-sm text-muted-foreground mt-1">{selected.grade}학년</p>
                    </div>
                    <div className="flex items-center gap-4">
                      <div className="text-center">
                        <div className="text-xs text-muted-foreground mb-1">초대 코드</div>
                        <div className="text-3xl font-mono font-bold tracking-widest text-primary">
                          {selected.invite_code}
                        </div>
                      </div>
                      <img
                        src={classroomApi.qrcodeUrl(selected.id)}
                        alt={`QR: ${selected.invite_code}`}
                        className="w-20 h-20 rounded-xl border"
                      />
                    </div>
                  </div>
                  <p className="text-xs text-muted-foreground mt-4 bg-muted/50 rounded-lg p-3">
                    학생들이 초대 코드 또는 QR코드로 접속하여 이름을 선택하거나 직접 입력하면 시험에 참여할 수 있습니다.
                  </p>
                </CardContent>
              </Card>

              {/* 학생 관리 */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center gap-2">
                    <Users className="w-4 h-4" />
                    학생 목록 ({studentList.length}명)
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="flex gap-2 mb-4 items-end">
                    <div className="flex-1">
                      <label className="text-xs text-muted-foreground mb-1 block">학생 이름</label>
                      <Input
                        value={studentName}
                        onChange={e => setStudentName(e.target.value)}
                        placeholder="예) 홍길동"
                        onKeyDown={e => e.key === 'Enter' && studentName.trim() && addStudentMutation.mutate()}
                      />
                    </div>
                    <div className="w-20">
                      <label className="text-xs text-muted-foreground mb-1 block">출석번호</label>
                      <Input
                        type="number"
                        value={studentNumber}
                        onChange={e => setStudentNumber(+e.target.value)}
                        min={1}
                        className="text-center"
                      />
                    </div>
                    <Button
                      onClick={() => addStudentMutation.mutate()}
                      disabled={!studentName.trim()}
                      size="sm"
                    >
                      추가
                    </Button>
                  </div>
                  <div className="max-h-52 overflow-y-auto">
                    <div className="grid grid-cols-2 gap-1.5">
                      {studentList.map((s: any) => (
                        editingStudent === s.id ? (
                          <div key={s.id} className="px-2 py-1.5 bg-primary/5 border border-primary/30 rounded-lg text-xs flex items-center gap-1.5">
                            <input
                              type="number"
                              value={editNumber}
                              onChange={e => setEditNumber(+e.target.value)}
                              min={1}
                              className="w-10 px-1 py-0.5 border rounded text-center text-[11px] bg-background"
                            />
                            <input
                              value={editName}
                              onChange={e => setEditName(e.target.value)}
                              className="flex-1 px-1.5 py-0.5 border rounded text-[11px] bg-background min-w-0"
                              autoFocus
                              onKeyDown={e => {
                                if (e.key === 'Enter' && editName.trim()) {
                                  updateStudentMutation.mutate({ studentId: s.id, data: { name: editName.trim(), student_number: editNumber } });
                                }
                                if (e.key === 'Escape') setEditingStudent(null);
                              }}
                            />
                            <button
                              onClick={() => updateStudentMutation.mutate({ studentId: s.id, data: { name: editName.trim(), student_number: editNumber } })}
                              disabled={!editName.trim()}
                              className="text-emerald-600 hover:text-emerald-700 disabled:opacity-30"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => { if (confirm(`${editName} 학생을 삭제하시겠습니까?`)) deleteStudentMutation.mutate(s.id); }}
                              className="text-destructive/50 hover:text-destructive"
                              title="학생 삭제"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                            <button onClick={() => setEditingStudent(null)} className="text-muted-foreground hover:text-foreground">
                              <X className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <div
                            key={s.id}
                            className="px-2.5 py-2 bg-muted/40 rounded-lg text-xs flex items-center gap-2 group cursor-pointer hover:bg-muted/60 transition-colors"
                            onClick={() => { setEditingStudent(s.id); setEditName(s.name); setEditNumber(s.student_number ?? 0); }}
                          >
                            <span className="text-muted-foreground font-mono text-[10px] w-5">
                              {String(s.student_number ?? 0).padStart(2, '0')}
                            </span>
                            <span className="font-medium flex-1">{s.name}</span>
                            <Pencil className="w-3 h-3 text-muted-foreground/30 group-hover:text-muted-foreground transition-opacity" />
                          </div>
                        )
                      ))}
                    </div>
                    {studentList.length === 0 && (
                      <p className="text-xs text-muted-foreground py-4 text-center">학생을 추가해주세요</p>
                    )}
                  </div>
                </CardContent>
              </Card>

              {/* 시험 배포 */}
              <Card>
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base flex items-center gap-2">
                      <ClipboardCheck className="w-4 h-4" />
                      배포된 시험
                    </CardTitle>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                      onClick={() => setShowDeploy(!showDeploy)}
                    >
                      <Plus className="w-3.5 h-3.5 mr-1" />
                      시험 배포
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {showDeploy && (
                    <div className="flex gap-2 mb-4 p-3 bg-emerald-50 dark:bg-emerald-950/30 rounded-lg border border-emerald-200/50">
                      <select
                        value={deployExamId}
                        onChange={e => setDeployExamId(e.target.value)}
                        className="flex-1 px-3 py-1.5 border rounded-lg text-sm bg-background"
                      >
                        <option value="">시험지 선택...</option>
                        {allExamList.map((e: any) => (
                          <option key={e.id} value={e.id}>
                            {e.title} ({e.total_questions}문항 · {e.total_points}점)
                            {e.status === 'EXAM_CONFIRMED' ? ' ✓' : ''}
                          </option>
                        ))}
                      </select>
                      <Button
                        onClick={() => deployMutation.mutate()}
                        disabled={!deployExamId}
                        size="sm"
                        className="bg-emerald-600 hover:bg-emerald-700 text-white"
                      >
                        배포
                      </Button>
                    </div>
                  )}


                  <div className="space-y-2">
                    {classExamList.map((ce: any) => (
                      <div key={ce.id} className="flex items-center justify-between px-4 py-3 border rounded-lg">
                        <div>
                          <div className="text-sm font-medium">{ce.exam_title || ce.exam_id}</div>
                          <div className="text-xs text-muted-foreground mt-0.5">
                            {ce.submission_count ?? 0}/{studentList.length}명 응시
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant={ce.status === 'active' ? 'default' : 'secondary'}>
                            {ce.status}
                          </Badge>
                          {ce.hwp_file_path && (
                            <a
                              href={classroomApi.downloadHwp(selectedId!, ce.id)}
                              target="_blank"
                              rel="noreferrer"
                              title="HWP 다운로드"
                            >
                              <Button variant="ghost" size="sm" className="h-7 w-7 p-0">
                                <Download className="w-3.5 h-3.5" />
                              </Button>
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                    {classExamList.length === 0 && (
                      <p className="text-xs text-muted-foreground py-6 text-center">
                        배포된 시험이 없습니다
                      </p>
                    )}
                  </div>
                </CardContent>
              </Card>
            </>
          ) : (
            <Card>
              <CardContent className="p-16 text-center text-muted-foreground text-sm">
                <School className="w-10 h-10 mx-auto mb-3 opacity-20" />
                <p>왼쪽에서 학급을 선택하세요</p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

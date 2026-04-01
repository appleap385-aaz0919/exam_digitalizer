import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
});

// 요청 인터셉터: JWT 토큰 자동 첨부
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// 응답 인터셉터: 401 → 로그인 페이지 (교사 전용)
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && typeof window !== 'undefined') {
      localStorage.removeItem('access_token');
      window.location.href = '/';
    }
    return Promise.reject(err);
  }
);

// 학생 전용 public API (401 리다이렉트 없음, 토큰 불필요)
const publicApi = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  headers: { 'Content-Type': 'application/json' },
});

export default api;

// ─── Auth ───────────────────────────────────────────
export const authApi = {
  login: (email: string, password: string) =>
    api.post('/auth/login', { email, password }),
  refresh: (refreshToken: string) =>
    api.post('/auth/refresh', { refresh_token: refreshToken }),
};

// ─── Learning Maps ──────────────────────────────────
export const learningMapApi = {
  getTree: (schoolLevel: string, grade: number, semester: number) =>
    api.get('/learning-maps/tree', { params: { school_level: schoolLevel, grade, semester } }),
  getNode: (nodeId: number) =>
    api.get(`/learning-maps/${nodeId}`),
  getQuestions: (nodeId: number, page = 1) =>
    api.get(`/learning-maps/${nodeId}/questions`, { params: { page } }),
};

// ─── Batches ────────────────────────────────────────
export const batchApi = {
  upload: (file: File, subject = '수학', grade?: number) => {
    const form = new FormData();
    form.append('file', file);
    return api.post(`/batches/upload?subject=${subject}${grade ? `&grade=${grade}` : ''}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  list: (page = 1) => api.get('/batches', { params: { page } }),
  get: (id: string) => api.get(`/batches/${id}`),
  getQuestions: (id: string, page = 1) => api.get(`/batches/${id}/questions`, { params: { page } }),
};

// ─── Questions ──────────────────────────────────────
export const questionApi = {
  list: (params?: Record<string, any>) => api.get('/questions', { params }),
  search: (params?: Record<string, any>) => api.get('/questions/search', { params }),
  get: (pkey: string) => api.get(`/questions/${pkey}`),
  getHistory: (pkey: string) => api.get(`/questions/${pkey}/history`),
};

// ─── Exams ──────────────────────────────────────────
export const examApi = {
  create: (data: any) => api.post('/exams', data),
  list: (params?: { page?: number; limit?: number }) =>
    api.get('/exams', { params: { page: 1, limit: 20, ...params } }),
  get: (id: string) => api.get(`/exams/${id}`),
  confirm: (id: string) => api.post(`/exams/${id}/confirm`),
  updatePoints: (examId: string, seq: number, points: number) =>
    api.patch(`/exams/${examId}/questions/${seq}/points`, { points }),
};

// ─── Classrooms ─────────────────────────────────────
export const classroomApi = {
  create: (data: { name: string; grade?: number }) => api.post('/classrooms', data),
  list: () => api.get('/classrooms'),
  get: (id: string) => api.get(`/classrooms/${id}`),
  addStudent: (classroomId: string, name: string, studentNumber?: number) =>
    api.post(`/classrooms/${classroomId}/students`, { name, student_number: studentNumber }),
  listStudents: (classroomId: string) => api.get(`/classrooms/${classroomId}/students`),
  updateStudent: (classroomId: string, studentId: number, data: { name?: string; student_number?: number }) =>
    api.patch(`/classrooms/${classroomId}/students/${studentId}`, data),
  deployExam: (classroomId: string, data: any) =>
    api.post(`/classrooms/${classroomId}/exams`, data),
  listExams: (classroomId: string) => api.get(`/classrooms/${classroomId}/exams`),
  downloadHwp: (classroomId: string, ceId: number) =>
    `${API_BASE}/api/v1/classrooms/${classroomId}/exams/${ceId}/download`,
};

// ─── Grades ─────────────────────────────────────────
export const gradeApi = {
  classroomExamSummary: (ceId: number) => api.get(`/grades/classroom-exam/${ceId}/summary`),
  examSummary: (examId: string) => api.get(`/grades/exam/${examId}/summary`),
  submission: (subId: number) => api.get(`/grades/submission/${subId}`),
};

// ─── Student Join (public — no auth redirect) ──────
export const studentApi = {
  findClassroom: (inviteCode: string) =>
    publicApi.get('/join/classroom', { params: { invite_code: inviteCode } }),
  selectStudent: (classroomId: string, studentId: number) =>
    publicApi.post('/join/select-student', { classroom_id: classroomId, student_id: studentId }),
  joinByName: (classroomId: string, name: string, studentNumber?: number) =>
    publicApi.post('/join/by-name', { classroom_id: classroomId, name, student_number: studentNumber }),
  getExams: (classroomId: string) =>
    publicApi.get(`/join/classroom/${classroomId}/exams`),
  getExamQuestions: (examId: string) =>
    publicApi.get(`/join/exam/${examId}/questions`),
};

// ─── Sessions (CBT) ────────────────────────────────
export const sessionApi = {
  start: (classroomExamId: number, studentToken: string) =>
    api.post('/sessions/start', { classroom_exam_id: classroomExamId }, {
      headers: { 'X-Student-Token': studentToken },
    }),
  submit: (sessionId: number, answers: any[], studentToken: string) =>
    api.post(`/sessions/${sessionId}/submit`, { answers }, {
      headers: { 'X-Student-Token': studentToken },
    }),
};

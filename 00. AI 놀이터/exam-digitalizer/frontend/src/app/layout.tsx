'use client';

import './globals.css';
import { QueryClient, QueryClientProvider, MutationCache } from '@tanstack/react-query';
import { useState } from 'react';
import { ToastProvider } from '@/components/ui/toast';

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <html lang="ko">
      <head>
        <title>시험 문항 디지털라이징 시스템</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css" />
        <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
        <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
          onLoad="renderMathInElement(document.body, {delimiters: [{left: '$$', right: '$$', display: true},{left: '$', right: '$', display: false},{left: '\\\\(', right: '\\\\)', display: false},{left: '\\\\[', right: '\\\\]', display: true}]});">
        </script>
      </head>
      <body className="min-h-screen">
        {/* MathType 수식 입력기 컨테이너 */}
        <div id="editorContainer" style={{ display: 'none', position: 'absolute', zIndex: 1000, width: 720, background: '#fff', boxShadow: '0 4px 20px rgba(0,0,0,0.2)', borderRadius: 8 }} />
        <script src="/common-mathtype.js" defer />
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            {children}
          </ToastProvider>
        </QueryClientProvider>
      </body>
    </html>
  );
}

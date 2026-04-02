'use client';

import { useEffect, useRef } from 'react';

interface MathRendererProps {
  html: string;
  className?: string;
}

/**
 * HTML 내 LaTeX 수식을 KaTeX로 렌더링하는 컴포넌트.
 * $...$ (인라인), $$...$$ (디스플레이), \(...\), \[...\] 지원.
 */
export function MathRenderer({ html, className = '' }: MathRendererProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current && typeof window !== 'undefined' && (window as any).renderMathInElement) {
      (window as any).renderMathInElement(ref.current, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false },
          { left: '\\(', right: '\\)', display: false },
          { left: '\\[', right: '\\]', display: true },
        ],
        throwOnError: false,
      });
    }
  }, [html]);

  return (
    <div
      ref={ref}
      className={className}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

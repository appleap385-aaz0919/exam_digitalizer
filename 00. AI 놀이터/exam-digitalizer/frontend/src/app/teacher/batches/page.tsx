'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { batchApi } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Upload, FileUp } from 'lucide-react';

export default function BatchesPage() {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<string | null>(null);

  const batches = useQuery({ queryKey: ['batches'], queryFn: () => batchApi.list() });

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setUploadResult(null);
    try {
      const res = await batchApi.upload(file);
      setUploadResult(`배치 ${res.data.batch_id} 생성 — 파싱 시작됨`);
      setFile(null);
      queryClient.invalidateQueries({ queryKey: ['batches'] });
    } catch (err: any) {
      setUploadResult(`업로드 실패: ${err.response?.data?.detail || err.message}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">HWP 파일 업로드</h1>
        <p className="text-muted-foreground text-sm mt-1">시험지를 올리면 AI가 자동으로 문항을 추출합니다</p>
      </div>

      <Card>
        <CardContent className="p-6">
          <div className="border-2 border-dashed border-muted-foreground/20 rounded-xl p-10 text-center hover:border-primary/40 transition-colors">
            <input type="file" accept=".hwp,.hwpx,.hwpml"
              onChange={(e) => setFile(e.target.files?.[0] || null)}
              className="hidden" id="hwp-upload" />
            <label htmlFor="hwp-upload" className="cursor-pointer">
              <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">
                {file ? file.name : 'HWP / HWPX / HWPML 파일을 선택하세요'}
              </p>
              <p className="text-xs text-muted-foreground/50 mt-1">또는 여기로 파일을 끌어놓으세요</p>
            </label>
          </div>
          {file && (
            <Button onClick={handleUpload} disabled={uploading} className="mt-4 w-full">
              <FileUp className="w-4 h-4 mr-2" />
              {uploading ? '업로드 중...' : '업로드 및 파싱 시작'}
            </Button>
          )}
          {uploadResult && (
            <div className={`mt-3 p-3 rounded-lg text-sm ${
              uploadResult.includes('실패') ? 'bg-destructive/10 text-destructive' : 'bg-emerald-50 text-emerald-700'
            }`}>
              {uploadResult}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">업로드 이력</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="divide-y">
            {(batches.data?.data.data ?? []).map((b: any) => (
              <div key={b.id} className="px-6 py-3.5 flex items-center justify-between">
                <div>
                  <span className="font-mono text-sm">{b.id}</span>
                  <span className="text-xs text-muted-foreground ml-2">{b.subject}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">{b.total_questions}문항</span>
                  <Badge variant={
                    b.status === 'COMPLETED' ? 'default' :
                    b.status === 'PARSING' ? 'secondary' : 'outline'
                  }>{b.status}</Badge>
                </div>
              </div>
            ))}
            {(batches.data?.data.data ?? []).length === 0 && (
              <div className="px-6 py-10 text-center text-sm text-muted-foreground">
                업로드된 배치가 없습니다
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface BulkUploadItem {
  file: string;
  job_id: string;
}

export interface FailedFileItem {
  file: string;
  error: string;
}

export interface BulkUploadResponse {
  status: string;
  message: string;
  items: BulkUploadItem[];
  failed_files?: FailedFileItem[];
}

export interface JobStatus {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  progress: number;
  error?: string;
}

@Injectable({ providedIn: 'root' })
export class BulkUploadService {
  private baseUrl = environment.backendApiUrl;

  constructor(private http: HttpClient) {}

  private getAuthHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });
  }

  bulkUpload(
    files: File[],
    filenameMap: Record<string, string> = {},
    transcriptionOptions: any = {},
  ): Observable<BulkUploadResponse> {
    const formData = new FormData();

    files.forEach((file) => formData.append('files', file, file.name));

    if (filenameMap && Object.keys(filenameMap).length > 0) {
      formData.append('custom_filenames', JSON.stringify(filenameMap));
    }

    try {
      const optsString = JSON.stringify(transcriptionOptions || {});
      formData.append('transcription_options', optsString);
    } catch {
      // If this fails, backend will reject; but we prefer pre-validation in component
      formData.append('transcription_options', '{}');
    }

    return this.http.post<BulkUploadResponse>(
      `${this.baseUrl}/api/process_audio_bulk`,
      formData,
      {
        headers: this.getAuthHeaders(),
      },
    );
  }

  getJobStatus(jobId: string): Observable<JobStatus> {
    return this.http.get<JobStatus>(`${this.baseUrl}/api/job-status/${jobId}`, {
      headers: this.getAuthHeaders(),
    });
  }
}

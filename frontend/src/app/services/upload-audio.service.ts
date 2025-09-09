import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface UploadResponse {
  job_id: string;
  status: string;
  message: string;
}

export interface JobStatus {
  id: string;
  status: string;
  created_at: string;
  updated_at: string;
  progress: number;
  error?: string;
}

@Injectable({
  providedIn: 'root',
})
export class UploadAudioService {
  constructor(private http: HttpClient) {}

  processAudio(file: File): Observable<any> {
    const formData = new FormData();
    formData.append('file', file);

    const token = localStorage.getItem('vEra_auth_token');

    const headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });

    return this.http.post<UploadResponse>(
      `${environment.backendApiUrl}/api/process_audio`,
      formData,
      {
        headers: headers,
        reportProgress: true,
        observe: 'events',
      },
    );
  }

  getJobStatus(jobId: string): Observable<JobStatus> {
    const token = localStorage.getItem('vEra_auth_token');
    const headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
    });

    return this.http.get<JobStatus>(
      `${environment.backendApiUrl}/api/job-status/${jobId}`,
      { headers },
    );
  }
}

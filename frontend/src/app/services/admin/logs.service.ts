import { Injectable } from '@angular/core';
import { HttpClient, HttpParams, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface LogFile {
  filename: string;
  size: number;
  last_modified: string;
  date: string;
}

export interface LogFilesResponse {
  log_files: LogFile[];
  total_count: number;
}

export interface LogContentResponse {
  filename: string;
  content: string;
  size: number;
  last_modified: string;
  total_lines: number;
}

@Injectable({
  providedIn: 'root'
})
export class LogsService {
  private readonly baseUrl = `${environment.backendApiUrl}/api/admin`;

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
  }

  /**
   * Get list of all log files
   */
  getLogFiles(): Observable<LogFilesResponse> {
    return this.http.get<LogFilesResponse>(`${this.baseUrl}/log-files`, { headers: this.getHeaders() });
  }

  /**
   * Get content of a specific log file
   */
  getLogFileContent(filename: string, lines?: number, search?: string): Observable<LogContentResponse> {
    let params = new HttpParams();
    
    if (lines !== undefined && lines > 0) {
      params = params.set('lines', lines.toString());
    }
    
    if (search && search.trim()) {
      params = params.set('search', search.trim());
    }

    return this.http.get<LogContentResponse>(`${this.baseUrl}/log-files/${encodeURIComponent(filename)}`, { 
      params, 
      headers: this.getHeaders() 
    });
  }
}

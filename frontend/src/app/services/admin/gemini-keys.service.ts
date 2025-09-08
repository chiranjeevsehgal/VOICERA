import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface GeminiKeysSummary {
  key_count: number;
  has_keys: boolean;
  rpm_limit: number;
  rps_limit: number;
  tpm_limit_raw: number;
  tpm_limit_effective: number;
  rpd_limit: number;
  cooldown_default_s: number;
}

export interface GeminiKeyStatusItem {
  key_prefix: string;
  cooldown_until: number;
  cooldown_remaining_s: number;
  rpm_last_min: number;
  rps_last_sec: number;
  tpm_last_min: number;
  daily_date: string;
  daily_count: number;
  error_counts: Record<string, number>;
}

export interface GeminiKeysStatusResponse {
  timestamp: number;
  summary: GeminiKeysSummary;
  keys: GeminiKeyStatusItem[];
}

@Injectable({ providedIn: 'root' })
export class GeminiKeysService {
  private readonly baseUrl = `${environment.apiUrl}/api/admin`;

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
  }

  getStatus(): Observable<GeminiKeysStatusResponse> {
    return this.http.get<GeminiKeysStatusResponse>(
      `${this.baseUrl}/gemini-keys/status`,
      { headers: this.getHeaders() }
    );
  }
}

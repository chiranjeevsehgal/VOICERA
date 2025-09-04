import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface UsageAnalyticsResponse {
  total_requests: number;
  average_response_time: number;
  endpoint_counts: Record<string, number>;
  // Other fields returned by API (we won't use them here)
  user_counts?: Record<string, number>;
  ip_counts?: Record<string, number>;
  date_range?: { start: string; end: string };
}

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private baseUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
  }

  getUsageAnalytics(): Observable<UsageAnalyticsResponse> {
    return this.http.get<UsageAnalyticsResponse>(
      `${this.baseUrl}/api/admin/analytics/usage`,
      { headers: this.getHeaders() }
    );
  }
}

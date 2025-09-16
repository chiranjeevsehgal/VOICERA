import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { environment } from '../../../environments/environment';
import { shouldUseMockData } from '../../utils/role.utils';

export interface UsageAnalyticsResponse {
  total_requests: number;
  average_response_time: number;
  min_response_time?: number;
  max_response_time?: number;
  endpoint_counts: Record<string, number>;
  user_counts?: Record<string, number>;
  ip_counts?: Record<string, number>;
  status_counts?: Record<string, number>;
  hourly_distribution?: Record<string, number>;
  date_range?: { start: string; end: string };
  endpoint_details?: EndpointDetail[];
  ip_details?: IPDetail[];
}

export interface EndpointDetail {
  endpoint: string;
  count: number;
  avg_response_time?: number;
  success_rate?: number;
}

export interface IPDetail {
  ip: string;
  count: number;
  avg_response_time?: number;
  last_seen?: string;
  first_seen?: string;
  unique_endpoints: number;
}

export interface IPDetailedAnalytics {
  ip_address: string;
  summary: {
    total_requests: number;
    unique_endpoints: number;
    unique_user_agents: number;
    unique_users: number;
    avg_response_time: number;
    first_seen: string;
    last_seen: string;
  };
  endpoints: Array<{
    endpoint: string;
    count: number;
    avg_response_time: number;
    last_accessed: string;
    success_rate: number;
  }>;
  hourly_pattern: Record<string, number>;
  daily_activity: Array<{
    date: string;
    requests: number;
    avg_response_time: number;
  }>;
  status_distribution: Record<string, number>;
  user_agents: string[];
  date_range: { start: string; end: string };
}

export interface RealTimeAnalytics {
  summary: {
    total_requests: number;
    unique_ips: number;
    unique_users: number;
    avg_response_time: number;
    error_rate: number;
    requests_per_minute: number;
  };
  timeline: Array<{
    timestamp: string;
    requests: number;
    avg_response_time: number;
    errors: number;
  }>;
  active_ips: Array<{
    ip: string;
    requests: number;
    last_seen: string;
    unique_endpoints: number;
  }>;
  top_endpoints: Array<{
    endpoint: string;
    requests: number;
    avg_response_time: number;
  }>;
  time_range: { start: string; end: string };
}

export interface AnalyticsFilters {
  days?: number;
  ip_address?: string;
  user_id?: string;
  endpoint?: string;
  status_code?: number;
  start_date?: string;
  end_date?: string;
}

@Injectable({ providedIn: 'root' })
export class AnalyticsService {
  private baseUrl = environment.backendApiUrl;

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
  }

  getUsageAnalytics(
    filters?: AnalyticsFilters,
  ): Observable<UsageAnalyticsResponse> {
    let params = new URLSearchParams();

    if (filters) {
      if (filters.days) params.append('days', filters.days.toString());
      if (filters.ip_address) params.append('ip_address', filters.ip_address);
      if (filters.user_id) params.append('user_id', filters.user_id);
      if (filters.endpoint) params.append('endpoint', filters.endpoint);
      if (filters.status_code)
        params.append('status_code', filters.status_code.toString());
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);
    }

    const url = `${this.baseUrl}/api/admin/analytics/usage${params.toString() ? '?' + params.toString() : ''}`;
    return this.http.get<UsageAnalyticsResponse>(url, {
      headers: this.getHeaders(),
    });
  }

  getIPDetailedAnalytics(
    ipAddress: string,
    days: number = 30,
  ): Observable<IPDetailedAnalytics> {
    return this.http.get<IPDetailedAnalytics>(
      `${this.baseUrl}/api/admin/analytics/ip-details/${encodeURIComponent(ipAddress)}?days=${days}`,
      { headers: this.getHeaders() },
    );
  }

  getRealTimeAnalytics(minutes: number = 60): Observable<RealTimeAnalytics> {
    return this.http.get<RealTimeAnalytics>(
      `${this.baseUrl}/api/admin/analytics/real-time?minutes=${minutes}`,
      { headers: this.getHeaders() },
    );
  }

  getFilteredUsageAnalytics(
    filters: AnalyticsFilters,
  ): Observable<UsageAnalyticsResponse> {
    return this.getUsageAnalytics(filters);
  }

  // Usage Map: aggregate ip_hits by country only
  getIpGeoSummary(): Observable<{ items: Array<{ country_code: string; country: string | null; count: number }> }> {
    // Check if we should use mock data (for guests or users without valid tokens)
    if (shouldUseMockData()) {
      // Return mock data for guests
      const mockData = {
        "items": [
          {"count": 1, "country_code": "IN", "country": "India"},
          {"count": 15, "country_code": "US", "country": "United States"},
          {"count": 8, "country_code": "BR", "country": "Brazil"},
          {"count": 23, "country_code": "CN", "country": "China"},
          {"count": 5, "country_code": "DE", "country": "Germany"},
          {"count": 12, "country_code": "JP", "country": "Japan"},
          {"count": 3, "country_code": "AU", "country": "Australia"},
          {"count": 19, "country_code": "CA", "country": "Canada"},
          {"count": 7, "country_code": "FR", "country": "France"},
          {"count": 11, "country_code": "GB", "country": "United Kingdom"},
          {"count": 4, "country_code": "IT", "country": "Italy"},
          {"count": 9, "country_code": "MX", "country": "Mexico"},
          {"count": 14, "country_code": "RU", "country": "Russia"},
          {"count": 6, "country_code": "ZA", "country": "South Africa"},
          {"count": 21, "country_code": "KR", "country": "South Korea"},
          {"count": 2, "country_code": "ES", "country": "Spain"},
          {"count": 16, "country_code": "AR", "country": "Argentina"},
          {"count": 10, "country_code": "EG", "country": "Egypt"},
          {"count": 18, "country_code": "NG", "country": "Nigeria"},
          {"count": 13, "country_code": "TH", "country": "Thailand"}
        ]
      };
      return of(mockData);
    }

    // For authenticated users, use real API
    const url = `${this.baseUrl}/api/admin/analytics/ip-geo-summary`;
    return this.http.get<{ items: Array<{ country_code: string; country: string | null; count: number }> }>(url, {
      headers: this.getHeaders(),
    });
  }
}

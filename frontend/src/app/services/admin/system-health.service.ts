import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

export interface CircuitBreakerState {
  name: string;
  state: 'closed' | 'open' | 'half_open';
  failure_count: number;
  success_count: number;
  last_failure_time: number;
  last_success_time: number;
  config: {
    failure_threshold: number;
    recovery_timeout: number;
    success_threshold: number;
    timeout: number;
  };
  stats: {
    total_requests: number;
    successful_requests: number;
    failed_requests: number;
    circuit_opens: number;
    circuit_closes: number;
  };
}

export interface SystemHealthResponse {
  status: string;
  circuit_breakers: { [key: string]: CircuitBreakerState };
  rate_limiter: {
    backend: string;
    cache_size: number | string;
  };
  total_circuit_breakers: number;
}

export interface CircuitBreakersResponse {
  circuit_breakers: { [key: string]: CircuitBreakerState };
  summary: {
    total: number;
    open: number;
    closed: number;
    half_open: number;
  };
}

export interface ResetCircuitBreakersResponse {
  status: string;
  message: string;
  reset_by: string;
}

export interface RateLimitConfig {
  limit: number;
  window: number;
}

export interface RateLimitsResponse {
  configuration: {
    endpoint_limits: { [key: string]: RateLimitConfig };
    user_limits: { [key: string]: RateLimitConfig };
    ip_limits: { [key: string]: RateLimitConfig };
  };
  limiter_status: {
    backend: string;
    local_cache_entries: number | string;
  };
}

@Injectable({
  providedIn: 'root'
})
export class SystemHealthService {
  private baseUrl = `${environment.backendApiUrl}/api/system`;

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    });
  }

  private handleError(error: any): Observable<never> {
    console.error('System Health API Error:', error);
    return throwError(() => error);
  }

  /**
   * Get overall system health
   */
  getSystemHealth(): Observable<SystemHealthResponse> {
    return this.http.get<SystemHealthResponse>(`${this.baseUrl}/health`, {
      headers: this.getHeaders()
    }).pipe(
      catchError(this.handleError)
    );
  }

  /**
   * Get detailed circuit breaker status
   */
  getCircuitBreakers(): Observable<CircuitBreakersResponse> {
    return this.http.get<CircuitBreakersResponse>(`${this.baseUrl}/circuit-breakers`, {
      headers: this.getHeaders()
    }).pipe(
      catchError(this.handleError)
    );
  }

  /**
   * Reset all circuit breakers
   */
  resetCircuitBreakers(): Observable<ResetCircuitBreakersResponse> {
    return this.http.post<ResetCircuitBreakersResponse>(`${this.baseUrl}/circuit-breakers/reset`, {}, {
      headers: this.getHeaders()
    }).pipe(
      catchError(this.handleError)
    );
  }

  /**
   * Get rate limiting configuration and status
   */
  getRateLimits(): Observable<RateLimitsResponse> {
    return this.http.get<RateLimitsResponse>(`${this.baseUrl}/rate-limits`, {
      headers: this.getHeaders()
    }).pipe(
      catchError(this.handleError)
    );
  }
}

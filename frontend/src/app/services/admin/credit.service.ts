import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface ApiIPCredit {
  id: string;
  ip: string;
  credits: number;
  created: string;
  last_used: string;
}

export interface ApiIPCreditsResponse {
  total_count: number;
  ip_credits: ApiIPCredit[];
}

export interface IPCredit {
  id: string;
  ip: string;
  credits: number;
  createdAt: Date;
  lastUsed: Date;
}

export interface ApiUpdateCreditResponse {
  id: string;
  ip: string;
  old_credits: number;
  new_credits: number;
  updated_at: string;
  updated_by: string;
}

export interface CreditRequestUser {
  full_name: string;
  email: string;
  role: string;
}

export interface ApiCreditRequest {
  _id: string;
  userInfo: CreditRequestUser;
  reason: string;
  ip_address: string;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  updated_at: string;
}

export interface ApiCreditRequestsResponse {
  status: boolean;
  requests: ApiCreditRequest[];
  total: number;
}

export interface CreditRequest {
  id: string;
  userInfo: CreditRequestUser;
  reason: string;
  ipAddress: string;
  status: 'pending' | 'approved' | 'rejected';
  createdAt: Date;
  updatedAt: Date;
}

@Injectable({
  providedIn: 'root',
})
export class CreditService {
  private baseUrl = environment.backendApiUrl;

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
  }

  getIPCredits(): Observable<ApiIPCreditsResponse> {
    return this.http.get<ApiIPCreditsResponse>(
      `${this.baseUrl}/api/admin/ip-credits`,
      {
        headers: this.getHeaders(),
      }
    );
  }

  updateIPCredits(
    ip: string,
    credits: number
  ): Observable<ApiUpdateCreditResponse> {
    return this.http.put<ApiUpdateCreditResponse>(
      `${this.baseUrl}/api/admin/ip-credits/${ip}/credits`,
      { credits },
      { headers: this.getHeaders() }
    );
  }

  // Transform API credit to component format
  transformApiCredit(apiCredit: ApiIPCredit): IPCredit {
    return {
      id: apiCredit.id,
      ip: apiCredit.ip,
      credits: apiCredit.credits,
      createdAt: new Date(apiCredit.created),
      lastUsed: new Date(apiCredit.last_used),
    };
  }

  getCreditRequests(): Observable<ApiCreditRequestsResponse> {
    return this.http.get<ApiCreditRequestsResponse>(
      `${this.baseUrl}/api/admin/credit-requests`,
      {
        headers: this.getHeaders(),
      }
    );
  }

  // TODO: Add API to update increase credit status
  updateCreditRequest(
    requestId: string,
    action: 'approve' | 'reject',
    creditsGranted?: number,
    reviewNotes?: string
  ): Observable<any> {
    const payload: any = { action };

    if (creditsGranted) {
      payload.credits_granted = creditsGranted;
    }

    if (reviewNotes) {
      payload.review_notes = reviewNotes;
    }

    return this.http.put(
      `${this.baseUrl}/api/admin/credit-requests/${requestId}`,
      payload,
      { headers: this.getHeaders() }
    );
  }

  // Transform API credit request to component format
  transformApiCreditRequest(apiRequest: ApiCreditRequest): CreditRequest {
    return {
      id: apiRequest._id,
      userInfo: apiRequest.userInfo,
      reason: apiRequest.reason,
      ipAddress: apiRequest.ip_address,
      status: apiRequest.status,
      createdAt: new Date(apiRequest.created_at),
      updatedAt: new Date(apiRequest.updated_at),
    };
  }
}

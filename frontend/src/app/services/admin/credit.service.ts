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

@Injectable({
  providedIn: 'root',
})
export class CreditService {
  private baseUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
  }

  getIPCredits(): Observable<ApiIPCreditsResponse> {
    return this.http.get<ApiIPCreditsResponse>(`${this.baseUrl}/api/admin/ip-credits`, {
      headers: this.getHeaders(),
    });
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
}
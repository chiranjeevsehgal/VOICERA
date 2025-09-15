import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { CreditRequestData } from '../components/request-credits-modal/request-credits-modal.component';
import { environment } from '../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class CreditRequestService {
  private baseUrl = environment.backendApiUrl;
  private authToken = localStorage.getItem('vEra_auth_token');

  constructor(private http: HttpClient) {}

  requestCredits(requestData: CreditRequestData): Observable<any> {
    const headers = new HttpHeaders({
      Authorization: `Bearer ${this.authToken}`,
      'Content-Type': 'application/json',
    });

    return this.http.post(`${this.baseUrl}/api/request-credits`, requestData, { headers });
  }
}
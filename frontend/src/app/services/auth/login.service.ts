import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { catchError, delay, Observable, tap, throwError } from 'rxjs';

interface LoginResponse {
  status: boolean;
  detail: string;
  access_token: string;
  token_type: string;
}

interface GuestLoginResponse {
  status: boolean;
  detail?: string;
  access_token: string;
  token_type: string;
  role?: string;
}

@Injectable({
  providedIn: 'root',
})
export class LoginService {
  constructor(private http: HttpClient) {}

  loginUser(userDetails: any) {
    const apiUrl = `${environment.backendApiUrl}/api/auth/login`;

    // Create a FormData object
    const formData = new FormData();
    formData.append('username', userDetails.email);
    formData.append('password', userDetails.password);

    return this.http.post<LoginResponse>(apiUrl, formData).pipe(
      tap((response) => {
        if (response.status == true) {
          localStorage.setItem('vEra_auth_token', response.access_token);
        }
      }),
    );
  }

  guestLogin(): Observable<GuestLoginResponse> {
    const apiUrl = `${environment.backendApiUrl}/api/auth/guest`;

    return this.http.post<GuestLoginResponse>(apiUrl, {}).pipe(
      tap((response) => {
        if (response.status === true) {
          localStorage.setItem('vEra_auth_token', response.access_token);
        }
      }),
      catchError((error) => {
        console.error('Guest login failed:', error);
        return throwError(() => error);
      }),
    );
  }

  exchangeGoogleCode(code: string): Observable<{
    access_token: string;
    detail?: string;
    role: string;
    token_type: string;
    status: boolean;
  }> {
    const payload = {
      code,
      provider: 'google',
    };

    return this.http.post<{
      access_token: string;
      detail?: string;
      role: string;
      token_type: string;
      status: boolean;
    }>(`${environment.backendApiUrl}/api/auth/oauth/callback`, payload);
  }

  exchangeGitHubCode(code: string): Observable<{
    access_token: string;
    detail?: string;
    role: string;
    token_type: string;
    status: boolean;
  }> {
    const payload = {
      code,
      provider: 'github',
    };

    return this.http.post<{
      access_token: string;
      detail?: string;
      role: string;
      token_type: string;
      status: boolean;
    }>(`${environment.backendApiUrl}/api/auth/oauth/callback`, payload);
  }
}

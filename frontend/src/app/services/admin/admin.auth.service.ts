import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { catchError, delay, Observable, tap, throwError } from 'rxjs';

interface LoginResponse {
  status: boolean,
  detail: string,
  access_token: string,
  token_type: string,
  role: string,
}

@Injectable({
  providedIn: 'root'
})
export class AdminAuthService {

  constructor(private http: HttpClient) { }

  loginUser(userDetails: any) {
    const apiUrl = `${environment.apiUrl}/api/auth/login`;

    // Create a FormData object
    const formData = new FormData();
    formData.append('username', userDetails.email);
    formData.append('password', userDetails.password);

    return this.http.post<LoginResponse>(apiUrl, formData).pipe(
      tap(response => {
        
        if (response.status == true && response.role == 'admin') {
          localStorage.setItem('auth_token', response.access_token);
        } else if (response.status == true && response.role !== 'admin') {
          throw new Error('You are not authorized.');
        }
      }), catchError(error => {
        if (error.message === 'You are not authorized.') {
          return throwError(() => ({ error: { detail: 'You are not authorized.' } }));
        }
        return throwError(() => error);
      })
    );
  }

  exchangeGoogleCode(code: string): Observable<{access_token: string;user: any;message?: string;token_type: string;status: boolean}> {
  const payload: {code: string;} = { code };
  
  return this.http.post<{access_token: string;user: any;message?: string;token_type: string;status: boolean}>(
    `${environment.apiUrl}/api/auth/google-login`,
    payload
  );
  }
}



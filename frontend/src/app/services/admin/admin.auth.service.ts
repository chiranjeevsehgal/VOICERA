import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import {
  BehaviorSubject,
  catchError,
  delay,
  Observable,
  of,
  tap,
  throwError,
} from 'rxjs';
import { UserProfile } from '../auth/profile.service';

interface LoginResponse {
  status: boolean;
  detail: string;
  access_token: string;
  token_type: string;
  role: string;
}

@Injectable({
  providedIn: 'root',
})
export class AdminAuthService {
  constructor(private http: HttpClient) {}
  private userProfileSubject = new BehaviorSubject<UserProfile | null>(null);

  loginUser(userDetails: any) {
    const apiUrl = `${environment.backendApiUrl}/api/auth/login`;

    // Create a FormData object
    const formData = new FormData();
    formData.append('username', userDetails.email);
    formData.append('password', userDetails.password);

    return this.http.post<LoginResponse>(apiUrl, formData).pipe(
      tap((response) => {
        if (response.status == true && response.role == 'admin') {
          localStorage.setItem('vEra_auth_token', response.access_token);
        } else if (response.status == true && response.role !== 'admin') {
          throw new Error('You are not authorized.');
        }
      }),
      catchError((error) => {
        if (error.message === 'You are not authorized.') {
          return throwError(() => ({
            error: { detail: 'You are not authorized.' },
          }));
        }
        return throwError(() => error);
      }),
    );
  }

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
  }

  get userProfile$(): Observable<UserProfile | null> {
    return this.userProfileSubject.asObservable();
  }

  getUserProfile(): Observable<UserProfile> {
    // First check localStorage
    const cachedProfile = localStorage.getItem('vEra_user_profile');

    if (cachedProfile) {
      try {
        const profile = JSON.parse(cachedProfile) as UserProfile;
        this.userProfileSubject.next(profile);
        // Return the cached profile as an observable
        return of(profile);
      } catch (error) {
        localStorage.removeItem('vEra_user_profile');
      }
    }

    // If no cached data, fetching from api
    const headers = this.getHeaders();
    return this.http
      .get<UserProfile>(`${environment.backendApiUrl}/api/auth/users/profile`, {
        headers,
      })
      .pipe(
        tap((profile) => {
          this.userProfileSubject.next(profile);
          localStorage.setItem('vEra_user_profile', JSON.stringify(profile));
        }),
        catchError((error) => {
          console.error('Error fetching user profile:', error);
          localStorage.removeItem('vEra_user_profile');
          throw error;
        }),
      );
  }

  // Method to load both profile and credits
  loadUserData(): void {
    this.getUserProfile().subscribe();
  }

  exchangeGoogleCode(code: string): Observable<{
    access_token: string;
    user: any;
    message?: string;
    token_type: string;
    status: boolean;
  }> {
    const payload: { code: string } = { code };

    return this.http.post<{
      access_token: string;
      user: any;
      message?: string;
      token_type: string;
      status: boolean;
    }>(`${environment.backendApiUrl}/api/auth/google-login`, payload);
  }
}

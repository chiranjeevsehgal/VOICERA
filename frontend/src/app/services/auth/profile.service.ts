import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, BehaviorSubject, of } from 'rxjs';
import { catchError, tap } from 'rxjs/operators';
import { environment } from '../../../environments/environment';

export interface UserProfile {
  email: string;
  full_name: string;
  role: string;
}

export interface CreditsResponse {
  ip_address: string;
  credits_remaining: number;
}

@Injectable({
  providedIn: 'root',
})
export class ProfileService {
  private baseUrl = environment.backendApiUrl;
  private userProfileSubject = new BehaviorSubject<UserProfile | null>(null);
  private creditsSubject = new BehaviorSubject<number>(0);

  // Public observables
  userProfile$ = this.userProfileSubject.asObservable();
  credits$ = this.creditsSubject.asObservable();

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
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
      .get<UserProfile>(`${this.baseUrl}/api/auth/users/profile`, { headers })
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

  getCredits(): Observable<CreditsResponse> {
    const headers = this.getHeaders();
    return this.http
      .get<CreditsResponse>(`${this.baseUrl}/api/check-credits`, { headers })
      .pipe(
        tap((response) => {
          this.creditsSubject.next(response.credits_remaining);
        }),
      );
  }

  // Method to get user initials for profile picture
  getUserInitials(fullName: string): string {
    if (!fullName) return '';
    const names = fullName.split(' ');
    if (names.length >= 2) {
      return (
        names[0][0].toUpperCase() + names[names.length - 1][0].toUpperCase()
      );
    }
    return names[0][0].toUpperCase();
  }

  // Method to load both profile and credits
  loadUserData(): void {
    this.getUserProfile().subscribe();
    this.getCredits().subscribe();
  }

  // Method to refresh credits only
  refreshCredits(): void {
    this.getCredits().subscribe();
  }

  // Getters for current values
  get currentUserProfile(): UserProfile | null {
    return this.userProfileSubject.value;
  }

  get currentCredits(): number {
    return this.creditsSubject.value;
  }
}

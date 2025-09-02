import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface ApiUser {
  id: string;
  email: string;
  full_name: string;
  status: 'active' | 'inactive';
  profile_picture?: string;
  role: 'admin' | 'user';
  created_at: string;
  auth_provider?: string;
}

export interface UpdateUserStatusRequest {
  status: 'active' | 'inactive';
}

export interface ApiUsersResponse {
  total_count: number;
  users: ApiUser[];
}

export interface User {
  id: string;
  name: string;
  email: string;
  role: 'admin' | 'user';
  status: 'active' | 'inactive';
  profilePicture?: string;
  authProvider?: string;
  createdAt: Date;
}

@Injectable({
  providedIn: 'root',
})
export class UserService {
  private baseUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
  }

  getUsers(): Observable<ApiUsersResponse> {
    return this.http.get<ApiUsersResponse>(`${this.baseUrl}/api/admin/users`, {
      headers: this.getHeaders(),
    });
  }

  updateUserStatus(
    userId: string,
    status: 'active' | 'inactive'
  ): Observable<ApiUser> {
    const body: UpdateUserStatusRequest = { status };
    return this.http.put<ApiUser>(
      `${this.baseUrl}/api/admin/users/${userId}`,
      body,
      { headers: this.getHeaders() }
    );
  }

  // Transform API user to component user format
  transformApiUser(apiUser: ApiUser): User {
    return {
      id: apiUser.id,
      name: apiUser.full_name,
      email: apiUser.email,
      role: apiUser.role,
      status: apiUser.status,
      profilePicture: apiUser.profile_picture,
      authProvider: apiUser.auth_provider,
      createdAt: new Date(apiUser.created_at),
    };
  }
}

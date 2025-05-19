import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import {environment } from "../../../environments/environment"
import { delay } from 'rxjs';

interface registerResponse {
  status : string,
  detail : string
}

@Injectable({
  providedIn: 'root'
})
export class RegisterService {

  constructor(private http: HttpClient) { }

  // private token = localStorage.getItem('auth_token');

  registerUser(userData: { fullName: string; email: string; password: string }) {
    const apiUrl = `${environment.apiUrl}/api/auth/register`;

    return this.http.post<registerResponse>(apiUrl, userData).pipe(
      delay(1200)
    );
  }
}

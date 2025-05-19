import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';
import { delay, tap } from 'rxjs';

interface LoginResponse {
  status: boolean,
  detail: string,
  access_token: string,
  token_type: string
}

@Injectable({
  providedIn: 'root'
})
export class LoginService {

  constructor(private http: HttpClient) { }

  loginUser(userDetails: any) {
    const apiUrl = `${environment.apiUrl}/api/auth/login`;

    // Create a FormData object
    const formData = new FormData();
    formData.append('username', userDetails.email);
    formData.append('password', userDetails.password);

    return this.http.post<LoginResponse>(apiUrl, formData).pipe(
      tap(resposne => {
        if (resposne.status == true) {
          localStorage.setItem('auth_token', resposne.access_token);
        }
      })
    );
  }
}

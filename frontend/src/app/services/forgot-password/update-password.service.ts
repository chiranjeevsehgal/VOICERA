import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';

interface PasswordUpdateResponse{
  status : string,
  detail : string
}

@Injectable({
  providedIn: 'root'
})
export class UpdatePasswordService {

  constructor(private http: HttpClient) { }

  updatepassword(email: string, otp: string, password: string) {

    const api = `${environment.apiUrl}/api/mail/update-password`;

    return this.http.post<PasswordUpdateResponse>(api, {
      otp :otp,
      email: email,
      password : password
    })
  }
}

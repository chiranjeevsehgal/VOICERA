import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../../environments/environment';

interface EmailVerificationResponse {
  status : boolean,
  detail : string
}

@Injectable({
  providedIn: 'root'
})
export class VerifyEmailService {

  constructor(
    private http : HttpClient
  ) { }

  verifyEmail(email : string){
    const api = `${environment.apiUrl}/api/mail/get-otp`;

    return this.http.post<EmailVerificationResponse>(api, {
      email : email
    })
  }
}

import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { environment } from '../../../environments/environment';

interface OtpVerificationResponse {
  status : boolean,
  detail : string
}

@Injectable({
  providedIn: 'root'
})
export class VerifyOtpService {

  constructor(private http: HttpClient) { }

  verifyOtp(email: string, otp: string) {
    const api = `${environment.apiUrl}/api/mail/verify-otp`;

    return this.http.post<OtpVerificationResponse>(api, {
      email: email,
      otp : otp
    })
  }
}

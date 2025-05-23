import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { InputOtp } from 'primeng/inputotp';
import { LucideAngularModule, Send } from 'lucide-angular';
import { VerifyOtpService } from '../../../services/forgot-password/verify-otp.service';
import { timeout } from 'rxjs';

@Component({
  selector: 'app-forgot-password-otp',
  imports: [
    InputOtp,
    FormsModule,
    LucideAngularModule
  ],
  templateUrl: './forgot-password-otp.component.html',
  styles: ``
})
export class ForgotPasswordOtpComponent {

  value: any;
  isSubmitting = false;
  readonly send = Send;

  @Input() email: string = "";

  @Output() otpVerified = new EventEmitter<boolean>();
  @Output() otp = new EventEmitter<string>();

  constructor(
    private otpVerificationService: VerifyOtpService
  ) {

  }

  onSubmit() {
    if (this.email != "") {
      this.isSubmitting = true;
      setTimeout(() => {

        this.otpVerificationService.verifyOtp(this.email, this.value).subscribe({
          next: (res) => {
            this.isSubmitting = false;
            // console.log(res);
            if (res.status) {
              // Emmiting the status and email
              this.otpVerified.emit(true);
              this.otp.emit(this.value);
            } else {
              // Emmiting the status
              this.otpVerified.emit(false);
            }
          },
          error: (error) => {
            this.isSubmitting = false;
            this.otpVerified.emit(false);
            // console.error(error);
          }
        })
      }, 2000);
    } else {
      console.error("Please Retry from step 1 : Email Varification");
    }
  }

}

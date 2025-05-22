import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { InputOtp } from 'primeng/inputotp';
import { LucideAngularModule, Send } from 'lucide-angular';

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

  value : any;
  isSubmitting = false;
  readonly send = Send;

}

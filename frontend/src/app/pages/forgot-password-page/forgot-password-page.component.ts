import { Component } from '@angular/core';
import { ForgotPasswordEmailComponent } from '../../components/forgot-password/forgot-password-email/forgot-password-email.component';
import { ForgotPasswordOtpComponent } from '../../components/forgot-password/forgot-password-otp/forgot-password-otp.component';
import { ForgotPasswordResetComponent } from '../../components/forgot-password/forgot-password-reset/forgot-password-reset.component';


@Component({
  selector: 'app-forgot-password-page',
  imports: [
    ForgotPasswordEmailComponent,
    ForgotPasswordOtpComponent,
    ForgotPasswordResetComponent
  ],
  templateUrl: './forgot-password-page.component.html',
  styles: ``
})
export class ForgotPasswordPageComponent {

}

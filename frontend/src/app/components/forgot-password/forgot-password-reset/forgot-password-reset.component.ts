import { Component } from '@angular/core';
import { LucideAngularModule, KeyRound, Eye, EyeOff } from 'lucide-angular';

@Component({
  selector: 'app-forgot-password-reset',
  imports: [
    LucideAngularModule
  ],
  templateUrl: './forgot-password-reset.component.html',
  styles: ``
})
export class ForgotPasswordResetComponent {

  isSubmitting: boolean = false;
  showPassword: boolean = false;

  // Icons
  readonly key = KeyRound;
  readonly eye = Eye;
  readonly eyeOff = EyeOff

  togglePasswordVisibility() {
    this.showPassword = !this.showPassword; // Toggle the visibility
  }
}

import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { LucideAngularModule, Fingerprint } from 'lucide-angular';


@Component({
  selector: 'app-forgot-password-email',
  imports: [
    CommonModule,
    ReactiveFormsModule,
    RouterModule,
    LucideAngularModule
  ],
  templateUrl: './forgot-password-email.component.html',
  styles: ``
})
export class ForgotPasswordEmailComponent {
  forgotPasswordForm: FormGroup;
  isSubmitting = false;
  readonly fingerPrint = Fingerprint;

  constructor(private fb: FormBuilder) {
    this.forgotPasswordForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]]
    });
  }

  onSubmit() {
    if (this.forgotPasswordForm.valid) {
      this.isSubmitting = true;

      // Here you would call your service to send reset instructions
      console.log('Sending reset instructions to:', this.forgotPasswordForm.value.email);

      // Simulate API call
      setTimeout(() => {
        this.isSubmitting = false;
        // Handle success or redirect
      }, 1500);
    } else {
      this.forgotPasswordForm.markAllAsTouched();
    }
  }
}

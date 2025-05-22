import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Output, output } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterModule } from '@angular/router';
import { LucideAngularModule, Fingerprint } from 'lucide-angular';
import { VerifyEmailService } from '../../../services/forgot-password/verify-email.service';
import { Toast } from 'primeng/toast';


@Component({
  selector: 'app-forgot-password-email',
  imports: [
    CommonModule,
    ReactiveFormsModule,
    RouterModule,
    LucideAngularModule
  ],
  templateUrl: './forgot-password-email.component.html',
})
export class ForgotPasswordEmailComponent {
  forgotPasswordForm: FormGroup;
  isSubmitting = false;
  readonly fingerPrint = Fingerprint;

  @Output() emailVerified = new EventEmitter<boolean>();
  @Output() email = new EventEmitter<string>();

  constructor(
    private fb: FormBuilder,
    private verifyEmailService : VerifyEmailService,
  ) {
    this.forgotPasswordForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]]
    });
  }

  onSubmit() {
    if (this.forgotPasswordForm.valid) {
      
      // Here you would call your service to send reset instructions
      console.log('Sending reset instructions to:', this.forgotPasswordForm.value.email);
      this.isSubmitting = true;
      
      // Simulate API call
      setTimeout(() => {
        // Handle success or redirect
        this.verifyEmailService.verifyEmail(this.forgotPasswordForm.value.email).subscribe({
          next : (res) => {
            this.isSubmitting = false;
            console.log(res);
            if(res.status){
              // Emmiting the status and email
              this.emailVerified.emit(true);
              this.email.emit(this.forgotPasswordForm.value.email);
            }else{
              // Emmiting the status
              this.emailVerified.emit(false);
            }
          },
          error : (error) => {
            this.isSubmitting = false;
            console.log(error);
          }
        })

      }, 1000);
    } else {
      this.forgotPasswordForm.markAllAsTouched();
    }
  }
}

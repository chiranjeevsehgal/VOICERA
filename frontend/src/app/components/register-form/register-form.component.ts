import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AbstractControl, FormBuilder, FormGroup, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { Toast } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { ProgressSpinner } from 'primeng/progressspinner';
import { RegisterService } from '../../services/auth/register.service';
import { Router } from '@angular/router';

@Component({
  selector: 'app-register-form',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    Toast,
    ProgressSpinner
  ],
  templateUrl: './register-form.component.html',
  providers: [
    MessageService
  ]
})
export class RegisterFormComponent {
  registerForm: FormGroup;
  isLoading: boolean = false;

  constructor(
    private fb: FormBuilder,
    private messageService: MessageService,
    private registerService: RegisterService,
    private router: Router
  ) {
    this.registerForm = this.fb.group({
      fullName: ['', Validators.required],
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, this.passwordStrengthValidator]]
    });
  }

  showToast() {
    this.messageService.add({ severity: 'info', summary: 'Info', detail: 'Message Content', life: 3000 });
  }

  // Custom validator for password strength
  passwordStrengthValidator(control: AbstractControl): ValidationErrors | null {
    const value = control.value || '';
    const hasUpperCase = /[A-Z]/.test(value);
    const hasLowerCase = /[a-z]/.test(value);
    const hasNumber = /\d/.test(value);
    const hasSpecialChar = /[!@#$%^&*(),.?":{}|<>]/.test(value);
    const isValidLength = value.length >= 8;

    const isStrong = hasUpperCase && hasLowerCase && hasNumber && hasSpecialChar && isValidLength;

    return isStrong ? null : { weakPassword: true };
  }

  onSubmit() {
    if (this.registerForm.valid) {
      this.isLoading = true;
      // console.log('Registration form submitted', this.registerForm.value);
      setTimeout(() => {
        this.registerService.registerUser(this.registerForm.value).subscribe({
          next: (response) => {
            // console.log('Registration successful:', response);
            this.registerForm.reset();
            this.isLoading = false;
            this.messageService.add({ severity: 'success', summary: 'Registration Successfull', detail: `${response.detail}`, life: 3000 });
            // Redirect to /login
            setTimeout(() => {
              this.router.navigate(['/login']);
            }, 2000);
          },
          error: (error) => {
            console.error('Registration failed:', error.error.detail);
            const detailMessage = Array.isArray(error?.error?.detail) && error.error.detail[0]?.msg
              ? error.error.detail[0].msg
              : typeof error?.error?.detail === 'string'
                ? error.error.detail
                : error?.error?.message
                  ? error.error.message
                  : 'An unexpected error occurred.';

            this.messageService.add({ severity: 'error', summary: 'Error', detail: detailMessage, life: 3000 });
            this.isLoading = false;
          }
        });
      }, 1000);

    }
  }
}
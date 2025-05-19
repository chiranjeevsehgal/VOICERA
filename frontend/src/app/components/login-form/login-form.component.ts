import { Component } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, AbstractControl, ValidationErrors } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ProgressSpinner } from 'primeng/progressspinner';
import { Toast } from 'primeng/toast';


@Component({
  selector: 'app-login-form',
  templateUrl: './login-form.component.html',
  styles: ``,
  imports: [
    Toast,
    ReactiveFormsModule,
    ProgressSpinner,
  ],
  providers: [
    MessageService
  ]
})
export class LoginFormComponent {
  loginForm: FormGroup;
  isLoading: boolean = false;

  constructor(
    private fb: FormBuilder,
    private messageService: MessageService,
  ) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, this.passwordStrengthValidator]]
    });
  }

  show() {
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
    if (this.loginForm.valid) {
      this.isLoading = true;
      console.log('Form submitted', this.loginForm.value);
    }
  }
}

import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { AbstractControl, FormBuilder, FormGroup, ReactiveFormsModule, ValidationErrors, Validators } from '@angular/forms';
import { LucideAngularModule, KeyRound, Eye, EyeOff } from 'lucide-angular';
import { UpdatePasswordService } from '../../../services/forgot-password/update-password.service';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-forgot-password-reset',
  imports: [
    LucideAngularModule,
    ReactiveFormsModule,
    CommonModule
  ],
  templateUrl: './forgot-password-reset.component.html',
  providers : [
    MessageService
  ]
})
export class ForgotPasswordResetComponent {

  isSubmitting: boolean = false;
  showPassword: boolean = false;
  confirmPasswordForm: FormGroup;

  @Input() email: string = "";
  @Input() otp: string = "";


  @Output() passwordUpdated = new EventEmitter<boolean>();
  @Output() password = new EventEmitter<string>();

  // Icons
  readonly key = KeyRound;
  readonly eye = Eye;
  readonly eyeOff = EyeOff

  constructor(
    private fb: FormBuilder,
    private updatePasswordService : UpdatePasswordService,
    private messageService : MessageService
  ) {
    this.confirmPasswordForm = this.fb.group({
      password: ['', [Validators.required,  this.passwordStrengthValidator]],
      confirmPassword: ['', [Validators.required]],
    }, { validators: this.passwordsMatchValidator });
  }

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

  passwordsMatchValidator(group: FormGroup): ValidationErrors | null {
    const password = group.get('password')?.value;
    const confirmPassword = group.get('confirmPassword')?.value;
    return password === confirmPassword ? null : { passwordsMismatch: true };
  }

  togglePasswordVisibility() {
    this.showPassword = !this.showPassword; // Toggle the visibility
  }

  onSubmit(){
    if(this.confirmPasswordForm.valid){
      this.isSubmitting = true;

      setTimeout(() => {
        this.updatePasswordService.updatepassword(this.email, this.otp, this.confirmPasswordForm.value.password).subscribe({
          next : (res) => {
            this.isSubmitting = false;
            // console.log(res);
            if(res.status){
              // Clear the from values
              this.confirmPasswordForm.reset
              // Emmiting the status and email
              this.passwordUpdated.emit(true);
              // this.email.emit(this.forgotPasswordForm.value.email);
            }else{
              // Emmiting the status
              this.passwordUpdated.emit(false);
            }
          },
          error : (error) => {
            this.isSubmitting = false;
            this.passwordUpdated.emit(false);
            console.error(error);
          }
        })
      }, 2000);
      
      
    }
  }
}

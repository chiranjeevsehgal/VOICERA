import { Component } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, AbstractControl, ValidationErrors } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ProgressSpinner } from 'primeng/progressspinner';
import { Toast } from 'primeng/toast';
import { LoginService } from '../../services/auth/login.service';


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
    private loginService: LoginService
  ) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required]]
    });
  }




  onSubmit() {
    if (this.loginForm.valid) {
      this.isLoading = true;
      // console.log('Form submitted', this.loginForm.value);

      setTimeout(() => {
        this.loginService.loginUser(this.loginForm.value).subscribe({
          next: (response) => {
            // console.log("Login Successfull", response);
            this.isLoading = false;
            this.router.navigate(['/search']);
            this.loginForm.reset();
          },
          error: (error) => {
            // console.log("Login Error", error);
            this.isLoading = false;
            this.messageService.add({ severity: 'error', summary: 'Error', detail: error.error.detail, life: 3000 });
          }
        })
      }, 3000);
    }
  }
}

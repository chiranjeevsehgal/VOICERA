import { Component, NgZone, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, AbstractControl, ValidationErrors } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ProgressSpinner } from 'primeng/progressspinner';
import { Toast } from 'primeng/toast';
import { LoginService } from '../../services/auth/login.service';
import { Router } from '@angular/router';


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
export class LoginFormComponent implements OnInit {
  loginForm: FormGroup;
  isLoading: boolean = false;

  ngOnInit(): void {
    // Initialize Google Sign-In
    this.initGoogleSignIn();
  }


  constructor(
    private fb: FormBuilder,
    private messageService: MessageService,
    private loginService: LoginService,
    private ngZone: NgZone,
    private router: Router
  ) {
    this.loginForm = this.fb.group({
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required]]
    });
  }

  initGoogleSignIn(): void {
    // @ts-ignore - Google is loaded via the script
    window.google?.accounts.id.initialize({
      client_id: '831027433891-violp93hiigrq3cm7t7kpdeavsmd5ek4.apps.googleusercontent.com',
      callback: this.handleGoogleSignIn.bind(this),
      auto_select: false,
      cancel_on_tap_outside: true,
      ux_mode: 'popup',
      context: 'signin'
    });

  }

  triggerGoogleSignIn(): void {
    // @ts-ignore - Google is loaded via the script
    window.google?.accounts.id.prompt();
  }

  handleGoogleSignIn(response: any): void {
    // Using NgZone because this callback runs outside Angular's zone
    this.ngZone.run(() => {
      this.isLoading = true;

      // Send the ID token to your backend
      this.loginService.googleLogin(response.credential).subscribe({
        next: (res) => {
          this.isLoading = false;
          if (res.status) {
            this.messageService.add({
              severity: 'success',
              summary: 'Success',
              detail: 'Login successful!'
            });
            this.router.navigate(['/']);
          } else {
            console.log(res);
            
            this.messageService.add({
              severity: 'error',
              summary: 'Error',
              detail: res.detail || 'Login failed'
            });
          }
        },
        error: (err) => {
          this.isLoading = false;

          this.messageService.add({
            severity: 'error',
            summary: 'Error',
            detail: err.error?.detail || 'Login failed'
          });
        }
      });
    });
  }






  onSubmit() {
    if (this.loginForm.valid) {
      this.isLoading = true;
      console.log('Form submitted', this.loginForm.value);

      setTimeout(() => {
        this.loginService.loginUser(this.loginForm.value).subscribe({
          next: (response) => {
            // console.log("Login Successfull", response);
            this.isLoading = false;
            this.messageService.add({ severity: 'success', summary: 'Success', detail: "Login Successful", life: 3000 });
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

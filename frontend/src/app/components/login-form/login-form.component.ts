import { Component, NgZone, OnInit } from '@angular/core';
import { FormBuilder, FormGroup, Validators, ReactiveFormsModule, AbstractControl, ValidationErrors } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ProgressSpinner } from 'primeng/progressspinner';
import { Toast } from 'primeng/toast';
import { LoginService } from '../../services/auth/login.service';
import { environment } from '../../../environments/environment';
import { LucideAngularModule, Eye, EyeOff } from 'lucide-angular';
import { Router } from '@angular/router';


@Component({
  selector: 'app-login-form',
  templateUrl: './login-form.component.html',
  styles: ``,
  imports: [
    Toast,
    ReactiveFormsModule,
    ProgressSpinner,
    LucideAngularModule
  ],
  providers: [
    MessageService
  ]
})
export class LoginFormComponent {
  loginForm: FormGroup;
  isLoading: boolean = false;
  showPassword: boolean = false;

  // Icons
  readonly eye = Eye;
  readonly eyeOff = EyeOff;

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

  togglePasswordVisibility() {
    this.showPassword = !this.showPassword; // Toggle the visibility
  }

  oauthSignIn() {
    // Google's OAuth 2.0 endpoint for requesting an access token
    var oauth2Endpoint = 'https://accounts.google.com/o/oauth2/v2/auth';

    var form = document.createElement('form');
    form.setAttribute('method', 'GET');
    form.setAttribute('action', oauth2Endpoint);


    // Passing to OAuth 2.0 endpoint.
    const params: { [key: string]: string } =
    {
      'client_id': environment.googleClientId,
      'redirect_uri': 'http://localhost:4200/auth/callback',
      'scope': 'openid email profile',
      'response_type': 'code',
      'include_granted_scopes': 'true',
      'state': 'pass-through value',
      'access_type': 'offline'
    };

    for (var p in params) {
      var input = document.createElement('input');
      input.setAttribute('type', 'hidden');
      input.setAttribute('name', p);
      input.setAttribute('value', params[p]);
      form.appendChild(input);
    }

    document.body.appendChild(form);
    form.submit();
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
            this.router.navigate(['/library']);
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

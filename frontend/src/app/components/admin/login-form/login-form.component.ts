import { Component, NgZone } from '@angular/core';
import { FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Eye, EyeOff, LucideAngularModule } from 'lucide-angular';
import { MessageService } from 'primeng/api';
import { ProgressSpinner } from 'primeng/progressspinner';
import { Toast } from 'primeng/toast';
import { Router } from '@angular/router';
import { environment } from '../../../../environments/environment';
import { AdminAuthService } from '../../../services/admin/admin.auth.service';

@Component({
  selector: 'admin-app-login-form',
  imports: [Toast,
    ReactiveFormsModule,
    ProgressSpinner,
    LucideAngularModule],
  templateUrl: './login-form.component.html',
  styles: ``,
  providers: [
    MessageService
  ]
})
export class AdminLoginFormComponent {
  loginForm: FormGroup;
  isLoading: boolean = false;
  showPassword: boolean = false;

  // Icons
  readonly eye = Eye;
  readonly eyeOff = EyeOff;

  constructor(
    private fb: FormBuilder,
    private messageService: MessageService,
    private adminloginService: AdminAuthService,
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
      'redirect_uri': `${environment.frontendApiUrl}/auth/callback`,
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
      setTimeout(() => {
        this.adminloginService.loginUser(this.loginForm.value).subscribe({
          next: (response) => {
            // console.log("Login Successfull", response);
            this.isLoading = false;
            this.messageService.add({ 
              severity: 'success', 
              summary: 'Success', 
              detail: 'Login successful! Redirecting...', 
              life: 2000 
            });

            setTimeout(() => {
              this.router.navigate(['/admin/dashboard']);
            }, 1000);

            this.loginForm.reset();
          },
          error: (error) => {
            console.log("Login Error", error);
            this.isLoading = false;
            this.messageService.add({ severity: 'error', summary: 'Error', detail: error.error.detail, life: 3000 });
          }
        })
      }, 3000);
    }
  }

}

import { Component, NgZone } from '@angular/core';
import { LoginService } from '../../services/auth/login.service';
import { environment } from '../../../environments/environment';
import { Router } from '@angular/router';
import { HotToastService } from '@ngxpert/hot-toast';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-login-form',
  templateUrl: './login-form.component.html',
  styles: `
    @keyframes wave {
      0%, 100% { transform: scaleY(1); }
      50% { transform: scaleY(0.5); }
    }
  `,
  imports: [CommonModule],
})
export class LoginFormComponent {
  isGuestLoading = false;

  constructor(
    private loginService: LoginService,
    private ngZone: NgZone,
    private router: Router,
    private toast: HotToastService
  ) {}

  oauthSignIn(provider: 'google' | 'github') {
    if (provider === 'google') {
      this.signInWithGoogle();
    } else if (provider === 'github') {
      this.signInWithGitHub();
    }
  }

  guestSignIn() {
    this.isGuestLoading = true;
    
    this.loginService.guestLogin().subscribe({
      next: (response) => {
        this.ngZone.run(() => {
          if (response.status) {
            localStorage.setItem('vEra_auth_token', response.access_token);
            this.toast.success('Welcome! Signed in as guest');
            this.router.navigate(['/library']);
          } else {
            this.toast.error(response.detail || 'Guest login failed');
          }
          this.isGuestLoading = false;
        });
      },
      error: (error) => {
        this.ngZone.run(() => {
          console.error('Guest login error:', error);
          this.toast.error('Failed to sign in as guest. Please try again.');
          this.isGuestLoading = false;
        });
      }
    });
  }

  private signInWithGoogle() {
    const oauth2Endpoint = 'https://accounts.google.com/o/oauth2/v2/auth';
    const form = document.createElement('form');
    form.setAttribute('method', 'GET');
    form.setAttribute('action', oauth2Endpoint);

    const params: { [key: string]: string } = {
      client_id: environment.googleClientId,
      redirect_uri: `${environment.frontendApiUrl}/auth/callback`,
      scope: 'openid email profile',
      response_type: 'code',
      include_granted_scopes: 'true',
      state: 'google-oauth',
      access_type: 'offline',
    };

    this.createFormAndSubmit(form, params);
  }

  private signInWithGitHub() {
    const oauth2Endpoint = 'https://github.com/login/oauth/authorize';
    const form = document.createElement('form');
    form.setAttribute('method', 'GET');
    form.setAttribute('action', oauth2Endpoint);

    const params: { [key: string]: string } = {
      client_id: environment.githubClientId,
      redirect_uri: 'http://localhost:4200/auth/callback',
      scope: 'read:user user:email',
      state: 'github-oauth',
    };

    this.createFormAndSubmit(form, params);
  }

  private createFormAndSubmit(
    form: HTMLFormElement,
    params: { [key: string]: string }
  ) {
    for (const key in params) {
      const input = document.createElement('input');
      input.setAttribute('type', 'hidden');
      input.setAttribute('name', key);
      input.setAttribute('value', params[key]);
      form.appendChild(input);
    }

    document.body.appendChild(form);
    form.submit();
  }
}
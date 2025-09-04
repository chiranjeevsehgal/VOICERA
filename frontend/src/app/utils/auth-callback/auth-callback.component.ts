import { Component, OnDestroy, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { LoginService } from '../../services/auth/login.service';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-auth-callback',
  imports: [CommonModule],
  templateUrl: './auth-callback.component.html',
  styles: `
      @keyframes fade-in-up {
      from {
        opacity: 0;
        transform: translateY(30px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
    
    .animate-fade-in-up {
      animation: fade-in-up 0.8s ease-out;
    }
    
    .animation-delay-150 {
      animation-delay: 150ms;
    }
    
    .animation-delay-300 {
      animation-delay: 300ms;
    }
  `,
})
export class AuthCallbackComponent implements OnInit, OnDestroy {
  isProcessing = true;
  progressWidth = 0;
  currentMessage = 'Connecting to Google...';
  subMessage = 'Please wait while we authenticate you';
  activeFeatureIndex = 0;

  private messageInterval: any;
  private progressInterval: any;
  private featureInterval: any;

  // Loading messages
  private messages = [
    {
      main: 'Connecting to Google...',
      sub: 'Establishing secure connection',
    },
    {
      main: 'Verifying your identity...',
      sub: "Google is confirming it's really you",
    },
    {
      main: 'Setting up your account...',
      sub: 'Preparing your personalized workspace',
    },
    {
      main: 'Loading your preferences...',
      sub: 'Customizing your VOICERA experience',
    },
    {
      main: 'Almost ready...',
      sub: 'Just a few more seconds!',
    },
  ];

  constructor(
    private router: Router,
    private route: ActivatedRoute,
    private loginService: LoginService
  ) {}

  ngOnInit(): void {
    this.startAnimations();
    this.handleAuthCallback();
    // setTimeout(() => {
    // }, 1000);
  }

  ngOnDestroy(): void {
    this.clearIntervals();
  }

  private startAnimations(): void {
    let messageIndex = 0;
    let progress = 0;

    this.progressInterval = setInterval(() => {
      if (progress < 85) {
        progress += Math.random() * 8;
        this.progressWidth = Math.min(progress, 85);
      }
    }, 500);

    this.messageInterval = setInterval(() => {
      if (messageIndex < this.messages.length - 1) {
        messageIndex++;
        this.currentMessage = this.messages[messageIndex].main;
        this.subMessage = this.messages[messageIndex].sub;
      }
    }, 2000);
  }

  private clearIntervals(): void {
    if (this.messageInterval) clearInterval(this.messageInterval);
    if (this.progressInterval) clearInterval(this.progressInterval);
    if (this.featureInterval) clearInterval(this.featureInterval);
  }

  private handleAuthCallback(): void {
    this.route.queryParams.subscribe((params) => {
      const code = params['code'];
      const state = params['state'];
      const error = params['error'];

      if (error) {
        console.error('OAuth error:', error);
        return;
      }

      if (code) {
        this.exchangeCodeForTokens(code);
      } else {
        console.error('No authorization code received');
      }
    });
  }

  private exchangeCodeForTokens(code: string): void {
    this.currentMessage = 'Finalizing authentication...';
    this.subMessage = 'Creating your secure session';

    this.progressWidth = 100;

    this.loginService.exchangeGoogleCode(code).subscribe({
      next: (response) => {
        // Check if account is inactive
        if (!response.status && response.detail?.includes('inactive')) {
          this.handleInactiveAccount(response.detail);
          return;
        }

        // Successful authentication
        this.currentMessage = 'Welcome to VOICERA!';
        this.subMessage = 'Redirecting to your dashboard...';
        localStorage.setItem('vEra_auth_token', response.access_token);

        setTimeout(() => {
          if (response.role == 'admin') {
            this.router.navigate(['/admin/dashboard']);
          } else {
            this.router.navigate(['/library']);
          }
        }, 1500);
      },
      error: (error) => {
        console.error('Failed to complete authentication');
        // Check if it's a 403 error (inactive account) or error response with inactive status
        if (
          error.status === 403 ||
          (error.error &&
            !error.error.status &&
            error.error.detail?.includes('inactive'))
        ) {
          const errorMessage =
            error.error?.detail ||
            'Your account is inactive. Please contact support.';
          this.handleInactiveAccount(errorMessage);
          return;
        }

        // For other errors, show generic error and redirect to login
        this.currentMessage = 'Authentication failed';
        this.subMessage = 'Redirecting to login...';

        setTimeout(() => {
          this.router.navigate(['/login'], {
            queryParams: {
              error: 'auth_failed',
              message: 'Authentication failed. Please try again.',
            },
          });
        }, 2000);
      },
    });
  }

  private handleInactiveAccount(detail: string): void {
    // Clear any existing intervals to stop message cycling
    this.clearIntervals();

    this.currentMessage = 'Account Inactive';
    this.subMessage = 'Redirecting to login...';

    setTimeout(() => {
      // Navigate to login with query parameter containing the error message
      this.router.navigate(['/login'], {
        queryParams: {
          error: 'account_inactive',
          message: detail,
        },
      });
    }, 2000);
  }
}

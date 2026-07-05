import { Component, OnDestroy, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { LoginService } from '../../services/auth/login.service';


@Component({
  selector: 'app-auth-callback',
  imports: [],
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

    /* Animated loader for messages */
    #load {
      position: absolute;
      width: min(600px, 90vw);
      height: 36px;
      left: 50%;
      top: 40%;
      transform: translateX(-50%);
      overflow: visible;
      -webkit-user-select: none;
      -moz-user-select: none;
      -ms-user-select: none;
      user-select: none;
      cursor: default;
    }

    #load div {
      position: absolute;
      width: 20px;
      height: 36px;
      opacity: 0;
      font-family: Helvetica, Arial, sans-serif;
      animation: move 2s linear infinite;
      transform: rotate(180deg);
      color: #35c4f0;
      font-weight: 600;
      letter-spacing: 1px;
      text-shadow: 0 0 8px rgba(53, 196, 240, 0.5);
    }

    @keyframes move {
      0% {
        left: 0;
        opacity: 0;
      }
      35% {
        left: 41%;
        transform: rotate(0deg);
        opacity: 1;
      }
      65% {
        left: 59%;
        transform: rotate(0deg);
        opacity: 1;
      }
      100% {
        left: 100%;
        transform: rotate(-180deg);
        opacity: 0;
      }
    }
  `,
})
export class AuthCallbackComponent implements OnInit, OnDestroy {
  isProcessing = true;
  progressWidth = 0;
  currentMessage = 'Connecting...';
  subMessage = 'Please wait while we authenticate you';
  activeFeatureIndex = 0;
  authProvider: 'google' | 'github' | null = null;

  private messageInterval: any;
  private progressInterval: any;
  private featureInterval: any;

  // Loading messages for different providers
  private googleMessages = [
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

  private githubMessages = [
    {
      main: 'Connecting to GitHub...',
      sub: 'Establishing secure connection',
    },
    {
      main: 'Verifying your identity...',
      sub: "GitHub is confirming it's really you",
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

  private get messages() {
    return this.authProvider === 'github'
      ? this.githubMessages
      : this.googleMessages;
  }

  constructor(
    private router: Router,
    private route: ActivatedRoute,
    private loginService: LoginService,
  ) {}

  ngOnInit(): void {
    this.determineAuthProvider();
    this.startAnimations();
    this.handleAuthCallback();
  }

  ngOnDestroy(): void {
    this.clearIntervals();
  }

  private determineAuthProvider(): void {
    this.route.queryParams.subscribe((params) => {
      const state = params['state'];

      // Determine provider based on state parameter
      if (state === 'google-oauth') {
        this.authProvider = 'google';
        this.currentMessage = 'Connecting to Google...';
      } else if (state === 'github-oauth') {
        this.authProvider = 'github';
        this.currentMessage = 'Connecting to GitHub...';
      } else {
        // Fallback - try to determine from URL or default to Google
        this.authProvider = 'google';
        this.currentMessage = 'Connecting...';
      }
    });
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

  // Split current message into characters for animated loader
  get messageChars(): string[] {
    return (this.currentMessage || '').split('');
  }

  private handleAuthCallback(): void {
    this.route.queryParams.subscribe((params) => {
      const code = params['code'];
      const state = params['state'];
      const error = params['error'];

      if (error) {
        console.error('OAuth error:', error);
        this.handleAuthError(error);
        return;
      }

      if (code && state) {
        this.exchangeCodeForTokens(code, state);
      } else {
        console.error('No authorization code or state received');
        this.handleAuthError('missing_params');
      }
    });
  }

  private exchangeCodeForTokens(code: string, state: string): void {
    this.currentMessage = 'Finalizing authentication...';
    this.subMessage = 'Creating your secure session';
    this.progressWidth = 100;

    // Determine which OAuth service to call based on state
    let authObservable;

    if (state === 'google-oauth') {
      authObservable = this.loginService.exchangeGoogleCode(code);
    } else if (state === 'github-oauth') {
      authObservable = this.loginService.exchangeGitHubCode(code);
    } else {
      console.error('Unknown OAuth provider state:', state);
      this.handleAuthError('unknown_provider');
      return;
    }

    authObservable.subscribe({
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
        console.error('Failed to complete authentication:', error);

        // Check if it's a 403 error (inactive account)
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
        this.handleAuthError(
          'auth_failed',
          error.error?.detail || 'Authentication failed. Please try again.',
        );
      },
    });
  }

  private handleAuthError(errorType: string, message?: string): void {
    this.clearIntervals();

    this.currentMessage = 'Authentication failed';
    this.subMessage = 'Redirecting to login...';

    setTimeout(() => {
      this.router.navigate(['/login'], {
        queryParams: {
          error: errorType,
          message: message || 'Authentication failed. Please try again.',
        },
      });
    }, 2000);
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

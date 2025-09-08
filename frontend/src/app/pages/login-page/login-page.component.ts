import { Component, OnInit } from '@angular/core';
import { LoginFormComponent } from '../../components/login-form/login-form.component';
import { ActivatedRoute, Router } from '@angular/router';
import { HotToastService } from '@ngxpert/hot-toast';

@Component({
  selector: 'app-login-page',
  template: `
    <div class="flex min-h-screen flex-col items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100 p-6 md:p-10">
      <div class="w-full max-w-sm md:max-w-4xl">
        <app-login-form></app-login-form>
      </div>
    </div>
  `,
  styles: ``,
  imports: [LoginFormComponent],
})
export class LoginPageComponent implements OnInit {
  constructor(
    private router: Router,
    private route: ActivatedRoute,
    private toast: HotToastService
  ) {}

  ngOnInit(): void {
    this.route.queryParams.subscribe((params) => {
      if (params['loggedOut'] === 'true') {
        this.toast.success('You have been logged out successfully.');
      }

      if (params['error']) {
        switch (params['error']) {
          case 'account_inactive':
            this.toast.error(
              params['message'] || 'Your account is inactive. Please contact support.',
              { id: 'account_inactive' }
            );
            break;
          case 'auth_failed':
            this.toast.error(
              params['message'] || 'Authentication failed. Please try again.',
              { id: 'auth_failed' }
            );
            break;
          default:
            if (params['message']) {
              this.toast.error(params['message'], { id: 'unknown_error' });
            }
            break;
        }
      }

      if (params['loggedOut'] || params['error']) {
        this.router.navigate([], {
          queryParams: {},
          replaceUrl: true,
        });
      }
    });
  }
}
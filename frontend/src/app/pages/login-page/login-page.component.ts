import { Component, OnInit } from '@angular/core';
import { LoginFormComponent } from '../../components/login-form/login-form.component';
import { ActivatedRoute, Router } from '@angular/router';
import { HotToastService } from '@ngxpert/hot-toast';

@Component({
  selector: 'app-login-page',
  templateUrl: './login-page.component.html',
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
    // Check for logout success message
    this.route.queryParams.subscribe((params) => {
      // Check for logout success message
      if (params['loggedOut'] === 'true') {
        this.toast.success('You have been logged out successfully.');
      }

      // Check for authentication errors
      if (params['error']) {
        switch (params['error']) {
          case 'account_inactive':
            this.toast.error(
              params['message'] ||
                'Your account is inactive. Please contact support for assistance.'
            );
            break;
          case 'auth_failed':
            this.toast.error(
              params['message'] || 'Authentication failed. Please try again.'
            );
            break;
          default:
            if (params['message']) {
              this.toast.error(params['message']);
            }
            break;
        }
      }

      // Clean up the query parameters after showing messages
      if (params['loggedOut'] || params['error']) {
        this.router.navigate([], {
          queryParams: {},
          replaceUrl: true,
        });
      }
    });
  }
}

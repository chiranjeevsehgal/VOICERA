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
  constructor(private router: Router, private route: ActivatedRoute, private toast:HotToastService) {}

  ngOnInit(): void {
    // Check for logout success message
    this.route.queryParams.subscribe((params) => {
      if (params['loggedOut'] === 'true') {
        this.toast.success('You have been logged out successfully.')
        // this.toast.error('Failed to load product. Please try again.')
        
        // Clean up the query parameter
        this.router.navigate([], {
          queryParams: {},
          replaceUrl: true,
        });
      }
    });
  }
}

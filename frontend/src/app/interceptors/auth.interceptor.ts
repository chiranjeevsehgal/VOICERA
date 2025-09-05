import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { HotToastService } from '@ngxpert/hot-toast';
import { MessageService } from 'primeng/api';
import { catchError, throwError } from 'rxjs';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  const toast = inject(HotToastService);

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      // Check if error is 401 and has the specific JWT expiration message
      if (
        error.status === 401 &&
        error.error?.detail === 'Could not validate credentials'
      ) {
        handleTokenExpiration(router, toast);
      }

      // Check for inactive account (403)
      console.log(error);      
      console.log(error.status);      
      console.log(error.error);      
      if (
        error.status === 403 &&
        error.error?.code === 'ACCOUNT_INACTIVE'
      ) {
        handleAccountInactive(router, toast);
      }

      return throwError(() => error);
    })
  );
};

function handleTokenExpiration(router: Router, toast: HotToastService): void {
  // Show  toast notification
  toast.error('Your session has expired. Please sign in again.', {
        id: 'session_expired',
  });

  // Remove from localStorage
  localStorage.removeItem('vEra_auth_token');
  localStorage.removeItem('vEra_user_profile');
  localStorage.removeItem('vEra_admin_current-view');

  // Small delay to show toast before redirect
  setTimeout(() => {
    router.navigate(['/login']);
  }, 100);
}

function handleAccountInactive(router: Router, toast: HotToastService): void {
  // Show error toast
  toast.error('Your account is inactive. Please contact support for assistance.',{
    id: 'account_inactive',
  });

  // Remove from localStorage
  localStorage.removeItem('vEra_auth_token');
  localStorage.removeItem('vEra_user_profile');
  localStorage.removeItem('vEra_admin_current-view');

  // Redirect to login
  setTimeout(() => {
    router.navigate(['/login']);
  }, 100);
}

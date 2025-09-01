import { HttpInterceptorFn, HttpErrorResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { MessageService } from 'primeng/api';
import { catchError, throwError } from 'rxjs';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  const messageService = inject(MessageService);

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      // Check if error is 401 and has the specific JWT expiration message
      if (error.status === 401 && 
          error.error?.detail === 'Could not validate credentials') {
        
        handleTokenExpiration(router, messageService);
      }
      
      return throwError(() => error);
    })
  );
};

function handleTokenExpiration(router: Router, messageService: MessageService): void {
  // Show  toast notification
  messageService.add({ 
    severity: 'error', 
    summary: 'Session Expired', 
    detail: 'Your session has expired. Please sign in again.', 
    life: 5000 
  });

  // Remove from localStorage
  localStorage.removeItem('auth_token');

  // Small delay to show toast before redirect
  setTimeout(() => {
    router.navigate(['/login']);
  }, 100);
}
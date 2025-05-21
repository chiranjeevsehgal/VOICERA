import { HttpClient } from '@angular/common/http';
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

export const authGuard: CanActivateFn = (route, state) => {
  const router = inject(Router);

  const token = localStorage.getItem('auth_token');

  if (!token) {
    console.warn("Token Missing");
    router.navigate(['/']);
    return false;
  } 

  return true;
};

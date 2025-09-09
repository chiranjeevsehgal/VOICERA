import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

export const redirectGuard: CanActivateFn = (route, state) => {
  const router = inject(Router);

  const token = localStorage.getItem('vEra_auth_token');

  if (token) {
    router.navigate(['/library']);
    return false;
  }

  return true;
};

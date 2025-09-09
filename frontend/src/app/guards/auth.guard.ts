import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

// Helper to extract role from JWT (supports role or roles[] claims)
const getRoleFromToken = (token: string): string | null => {
  try {
    const base64 = token.split('.')[1];
    if (!base64) return null;
    const base64url = base64.replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(atob(base64url));
    if (typeof payload.role === 'string') return payload.role;
    if (Array.isArray(payload.roles)) {
      return payload.roles.includes('admin') ? 'admin' : null;
    }
    return null;
  } catch {
    return null;
  }
};

export const authGuard: CanActivateFn = (route, state) => {
  const router = inject(Router);

  const token = localStorage.getItem('vEra_auth_token');

  if (!token) {
    console.warn('Token Missing');
    router.navigate(['/']);
    return false;
  }

  // Restrict access to admin dashboard to admin role only
  if (state.url.startsWith('/admin/')) {
    const role = getRoleFromToken(token);
    if (role === 'user') {
      router.navigate(['/library']);
      return false;
    }
  }

  return true;
};

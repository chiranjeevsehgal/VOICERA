/**
 * Extract role from JWT token
 */
export function getRoleFromToken(token: string): string | null {
  try {
    const base64 = token.split('.')[1];
    if (!base64) return null;
    
    const base64url = base64.replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(atob(base64url));
    
    // Check for single role
    if (typeof payload.role === 'string') {
      return payload.role;
    }
    
    // Check for roles array
    if (Array.isArray(payload.roles)) {
      return payload.roles.includes('admin') ? 'admin' : payload.roles[0] || null;
    }
    
    return null;
  } catch {
    return null;
  }
}

/**
 * Get current user role from localStorage token
 */
export function getCurrentUserRole(): string | null {
  const token = localStorage.getItem('vEra_auth_token');
  if (!token) return null;
  return getRoleFromToken(token);
}

/**
 * Check if current user is guest
 */
export function isGuest(): boolean {
  const token = localStorage.getItem('vEra_auth_token');
  if (!token) return false;
  
  try {
    const base64 = token.split('.')[1];
    if (!base64) return false;
    
    const base64url = base64.replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(atob(base64url));
    
    return payload.is_guest === true || payload.role === 'guest';
  } catch {
    return false;
  }
}

/**
 * Check if user should see mock data
 */
export function shouldUseMockData(): boolean {
  return isGuest();
}
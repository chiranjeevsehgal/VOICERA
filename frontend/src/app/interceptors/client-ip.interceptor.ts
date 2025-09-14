import { HttpInterceptorFn } from '@angular/common/http';
import { from, of } from 'rxjs';
import { catchError, map, switchMap } from 'rxjs/operators';
import { environment } from '../../environments/environment';

function fetchPublicIp$() {
  // Use fetch directly to avoid HttpClient recursion inside interceptor
  return from(fetch('https://api.ipify.org?format=json', { cache: 'reload' })).pipe(
    switchMap((res) => res.json()),
    map((json: any) => json?.ip as string),
    catchError(() => of<string | null>(null))
  );
}

export const clientIpInterceptor: HttpInterceptorFn = (req, next) => {
  // Skip non-HTTP(s) requests
  const isHttp = req.url.startsWith('http://') || req.url.startsWith('https://') || req.url.startsWith('/');
  if (!isHttp) {
    return next(req);
  }

  const token = localStorage.getItem('client_ip_header_token') || undefined; // Optional dev token

  // Decide whether to attach the header only for our backend or same-origin routes
  let shouldAttach = false;
  try {
    const backendOrigin = new URL(environment.backendApiUrl).origin;
    if (req.url.startsWith('http://') || req.url.startsWith('https://')) {
      const requestOrigin = new URL(req.url).origin;
      shouldAttach = requestOrigin === backendOrigin;
    } else if (req.url.startsWith('/')) {
      // Relative URLs are same-origin to the Angular app
      shouldAttach = true;
    }
  } catch {
    // If parsing fails, be conservative and only add for relative URLs
    shouldAttach = req.url.startsWith('/');
  }

  if (!shouldAttach) {
    // Bypass modification for third-party domains (e.g., https://api.pexels.com)
    return next(req);
  }

  // Always fetch fresh IP on every qualified request - no caching
  return fetchPublicIp$().pipe(
    switchMap((ip) => {
      if (ip) {
        const withIp = req.clone({
          setHeaders: {
            'X-Client-IP': ip,
            ...(token ? { 'X-Client-IP-Token': token } : {}),
          },
        });
        return next(withIp);
      }
      return next(req);
    })
  );
};

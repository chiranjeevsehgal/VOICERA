import { HttpInterceptorFn } from '@angular/common/http';
import { from, of } from 'rxjs';
import { catchError, map, switchMap } from 'rxjs/operators';

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

  // Always fetch fresh IP on every request - no caching
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

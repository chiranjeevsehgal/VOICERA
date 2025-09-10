import { HttpInterceptorFn } from '@angular/common/http';
import { from, of } from 'rxjs';
import { catchError, map, switchMap, tap } from 'rxjs/operators';

function getCachedIp(): string | null {
  try {
    const raw = localStorage.getItem('client_public_ip');
    const ts = localStorage.getItem('client_public_ip_ts');
    if (!raw || !ts) return null;
    const ageMs = Date.now() - Number(ts);
    // Reuse cached value for up to 24 hours
    if (ageMs < 24 * 60 * 60 * 1000) return raw;
  } catch {}
  return null;
}

function cacheIp(ip: string) {
  try {
    localStorage.setItem('client_public_ip', ip);
    localStorage.setItem('client_public_ip_ts', String(Date.now()));
  } catch {}
}

function fetchPublicIp$() {
  // Use fetch directly to avoid HttpClient recursion inside interceptor
  return from(fetch('https://api.ipify.org?format=json', { cache: 'reload' })).pipe(
    switchMap((res) => res.json()),
    map((json: any) => json?.ip as string),
    tap((ip) => ip && cacheIp(ip)),
    catchError(() => of<string | null>(null))
  );
}

export const clientIpInterceptor: HttpInterceptorFn = (req, next) => {
  // Skip non-HTTP(s) requests
  const isHttp = req.url.startsWith('http://') || req.url.startsWith('https://') || req.url.startsWith('/');
  if (!isHttp) {
    return next(req);
  }

  const cached = getCachedIp();
  const token = localStorage.getItem('client_ip_header_token') || undefined; // Optional dev token

  if (cached) {
    const withIp = req.clone({
      setHeaders: {
        'X-Client-IP': cached,
        ...(token ? { 'X-Client-IP-Token': token } : {}),
      },
    });
    return next(withIp);
  }

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

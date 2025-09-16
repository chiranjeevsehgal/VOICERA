import { Injectable } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { filter } from 'rxjs/operators';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class IpPingService {
  private readonly LS_KEY_LAST_AT = 'ip_ping_last_at';
  // Ping at most once per 12 hours
  private readonly TTL_MS = 12 * 60 * 60 * 1000;
  private initialized = false;

  constructor(private readonly http: HttpClient, private readonly router: Router) {
    // Fire one ping eagerly on app start
    this.pingIfNeeded();

    // Also watch for navigations; on the first nav (and thereafter after TTL), ping
    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe(() => {
        this.pingIfNeeded();
      });
  }

  private shouldPing(): boolean {
    try {
      const lastAtRaw = localStorage.getItem(this.LS_KEY_LAST_AT);
      if (!lastAtRaw) return true;
      const lastAt = parseInt(lastAtRaw, 10);
      if (Number.isNaN(lastAt)) return true;
      return Date.now() - lastAt > this.TTL_MS;
    } catch {
      return true;
    }
  }

  private markPinged() {
    try {
      localStorage.setItem(this.LS_KEY_LAST_AT, String(Date.now()));
    } catch {
      // ignore storage failures
    }
  }

  private pingIfNeeded() {
    if (!this.shouldPing()) return;
    // Use absolute backend URL; backend middleware will record the IP uniquely.
    const url = `${environment.backendApiUrl.replace(/\/$/, '')}/api/ip`;
    this.http
      .get(url, { responseType: 'json' })
      .subscribe({
        next: () => this.markPinged(),
        error: () => {
          // do not mark as pinged on error so we can retry later
        },
      });
  }
}

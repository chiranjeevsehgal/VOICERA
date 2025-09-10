import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideRouter, TitleStrategy } from '@angular/router';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { providePrimeNG } from 'primeng/config';

import { routes } from './app.routes';
import { Noir } from '../../Noir';
import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { authInterceptor } from './interceptors/auth.interceptor';
import { clientIpInterceptor } from './interceptors/client-ip.interceptor';
import { provideHotToastConfig } from '@ngxpert/hot-toast';
import { AppTitleStrategy } from './title.strategy';

export const appConfig: ApplicationConfig = {
  providers: [
    provideHttpClient(withInterceptors([clientIpInterceptor, authInterceptor])),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    { provide: TitleStrategy, useClass: AppTitleStrategy },
    provideAnimationsAsync(),
    providePrimeNG({
      theme: {
        preset: Noir,
        options: {
          darkModeSelector: false || 'none',
        },
      },
    }),
    provideHotToastConfig({
      duration: 3000,
      position: 'top-center',
    }),
  ],
};

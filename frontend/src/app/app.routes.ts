import { Routes } from '@angular/router';
import { LoginPageComponent } from './pages/login-page/login-page.component';
import { SearchComponent } from './pages/search/search.component';
import { RegisterPageComponent } from './pages/register-page/register-page.component';
import { PageNotFound } from './pages/error-page/error-page';
import { authGuard } from './guards/auth.guard';
import { redirectGuard } from './guards/redirect.guard';
import { ForgotPasswordPageComponent } from './pages/forgot-password-page/forgot-password-page.component';
import { AuthCallbackComponent } from './utils/auth-callback/auth-callback.component';
import { AdminLoginPageComponent } from './pages/admin/login-page/login-page.component';
import { AdminDashboardComponent } from './pages/admin/dashboard/dashboard.component';
import { SemanticSearchComponent } from './pages/semantic-search/semantic-search.component';
import { UploadComponent } from './pages/upload/upload.component';
import { UploadTrackingComponent } from './pages/upload-tracking/upload-tracking.component';


export const routes: Routes = [

    {path: "", redirectTo: "login", pathMatch: "full" },
    {path:"login", component: LoginPageComponent, canActivate : [redirectGuard]},
    {path:"library", component: SearchComponent, canActivate : [authGuard]},
    {path:"ai-search", component: SemanticSearchComponent, canActivate : [authGuard]},
    {path:"upload", component: UploadComponent, canActivate : [authGuard]},
    {path:"track", component: UploadTrackingComponent, canActivate : [authGuard]},
    {path:"register", component: RegisterPageComponent, canActivate : [redirectGuard]},
    {path:"forgot-password", component: ForgotPasswordPageComponent},
    {path:"auth/callback", component: AuthCallbackComponent},
    
    // Admin route
    {
        path: 'admin',
        canActivate: [],
        children: [
            //   { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
            { path: '', redirectTo: 'login', pathMatch: 'full' },
            { path: 'login', component: AdminLoginPageComponent },
            { path: 'dashboard', component: AdminDashboardComponent },
        ]
    },
    {path: "**", component: PageNotFound},

];

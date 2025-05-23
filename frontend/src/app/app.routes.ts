import { Routes } from '@angular/router';
import { LoginPageComponent } from './pages/login-page/login-page.component';
import { SearchComponent } from './pages/search/search.component';
import { RegisterPageComponent } from './pages/register-page/register-page.component';
import { PageNotFound } from './pages/error-page/error-page';
import { authGuard } from './guards/auth.guard';
import { redirectGuard } from './guards/redirect.guard';
import { AuthCallbackComponent } from './utils/auth-callback/auth-callback.component';
import { AdminLoginPageComponent } from './pages/admin/login-page/login-page.component';
import { AdminDashboardComponent } from './pages/admin/dashboard/dashboard.component';


export const routes: Routes = [

    {path: "", redirectTo: "login", pathMatch: "full" },
    {path:"login", component: LoginPageComponent, canActivate : [redirectGuard]},
    {path:"search", component: SearchComponent, canActivate : [authGuard]},
    {path:"register", component: RegisterPageComponent, canActivate : [redirectGuard]},
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

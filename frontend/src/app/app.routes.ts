import { Routes } from '@angular/router';
import { LoginPageComponent } from './pages/login-page/login-page.component';
import { SearchComponent } from './pages/search/search.component';
import { RegisterPageComponent } from './pages/register-page/register-page.component';
import { PageNotFound } from './pages/error-page/error-page';
import { authGuard } from './guards/auth.guard';
import { redirectGuard } from './guards/redirect.guard';
import { ForgotPasswordPageComponent } from './pages/forgot-password-page/forgot-password-page.component';


export const routes: Routes = [

    {path: "", redirectTo: "login", pathMatch: "full" },
    {path:"login", component: LoginPageComponent, canActivate : [redirectGuard]},
    {path:"search", component: SearchComponent, canActivate : [authGuard]},
    {path:"register", component: RegisterPageComponent, canActivate : [redirectGuard]},
    {path:"forgot-password", component: ForgotPasswordPageComponent},
    {path: "**", component: PageNotFound},
];

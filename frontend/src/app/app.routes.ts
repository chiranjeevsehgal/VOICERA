import { Routes } from '@angular/router';
import { LoginPageComponent } from './pages/login-page/login-page.component';
import { SearchComponent } from './pages/search/search.component';
import { RegisterPageComponent } from './pages/register-page/register-page.component';
import { PageNotFound } from './pages/error-page/error-page';


export const routes: Routes = [

    {path: "", redirectTo: "login", pathMatch: "full" },
    {path:"login", component: LoginPageComponent},
    {path:"search", component: SearchComponent},
    {path:"register", component: RegisterPageComponent},
    {path: "**", component: PageNotFound},
];

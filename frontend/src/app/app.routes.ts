import { Routes } from '@angular/router';
import { LoginPageComponent } from './pages/login-page/login-page.component';
import { SearchComponent } from './pages/search/search.component';
import { RegisterPageComponent } from './pages/register-page/register-page.component';


export const routes: Routes = [

    {path:"login", component: LoginPageComponent},
    {path:"search", component: SearchComponent},
    {path:"register", component: RegisterPageComponent},
    { path: "", redirectTo: "login", pathMatch: "full" }
];

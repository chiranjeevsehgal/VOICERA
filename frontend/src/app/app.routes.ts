import { Routes } from '@angular/router';
import { LoginPageComponent } from './pages/login-page/login-page.component';
import { SearchComponent } from './pages/search/search.component';

export const routes: Routes = [

    {path:"login", component: LoginPageComponent},
    {path:"search", component: SearchComponent},
];

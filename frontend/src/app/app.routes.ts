import { Routes } from '@angular/router';
import { LoginPageComponent } from './pages/login-page/login-page.component';
import { SearchComponent } from './pages/search/search.component';
import { PageNotFound } from './pages/error-page/error-page';
import { authGuard } from './guards/auth.guard';
import { redirectGuard } from './guards/redirect.guard';
import { AuthCallbackComponent } from './utils/auth-callback/auth-callback.component';
import { AdminDashboardComponent } from './pages/admin/dashboard/dashboard.component';
import { ApplicationLogsComponent } from './components/admin/application-logs/application-logs.component';
import { LogViewerComponent } from './components/admin/log-viewer/log-viewer.component';
import { SemanticSearchComponent } from './pages/semantic-search/semantic-search.component';
import { UploadComponent } from './pages/upload/upload.component';
import { UploadTrackingComponent } from './pages/upload-tracking/upload-tracking.component';
import { AiAnswerComponent } from './pages/ai-answer/ai-answer.component';


export const routes: Routes = [

    {path: "", redirectTo: "login", pathMatch: "full" },
    {path:"login", component: LoginPageComponent, canActivate : [redirectGuard], title: 'Login'},
    {path:"library", component: SearchComponent, canActivate : [authGuard], title: 'Library'},
    {path:"ai-search", component: SemanticSearchComponent, canActivate : [authGuard], title: 'AI Search'},
    {path:"ai-answer", component: AiAnswerComponent, canActivate : [authGuard], title: 'AI Answer'},
    {path:"upload", component: UploadComponent, canActivate : [authGuard], title: 'Upload'},
    {path:"track", component: UploadTrackingComponent, canActivate : [authGuard], title: 'Upload Tracking'},
    {path:"auth/callback", component: AuthCallbackComponent, title: 'Authenticating'},
    
    // Admin route
    {
        path: 'admin',
        canActivate: [
            authGuard
        ],
        children: [
            { path: '', redirectTo: 'login', pathMatch: 'full' },
            { path: 'dashboard', component: AdminDashboardComponent, title: 'Admin Dashboard' },
            { path: 'application-logs', component: ApplicationLogsComponent, title: 'Application Logs' },
            { path: 'application-logs/:filename', component: LogViewerComponent, title: 'Log Viewer' },
        ]
    },
    {path: "**", component: PageNotFound, title: 'Not Found'},

];

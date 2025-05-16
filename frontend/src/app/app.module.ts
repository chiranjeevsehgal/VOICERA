import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { providePrimeNG } from 'primeng/config';
import { Noir } from '../../Noir';
import Material from '@primeng/themes/material';

import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';
import { SearchComponent } from './pages/search/search.component';
import { RouterModule } from '@angular/router';
import { HeaderComponent } from './components/header/header.component';
import { SerachSectionComponent } from './components/search-section/search-section.component';
import { PodcastGridComponent } from './components/podcast-grid/podcast-grid.component';
import { PodcastCardComponent } from './components/podcast-card/podcast-card.component';
import { TrendingSearchesComponent } from './components/trending-searches/trending-searches.component';
import { LoginFormComponent } from './components/login-form/login-form.component';
import { LandingPageComponent } from './pages/landing-page/landing-page.component';
import { CommonModule } from '@angular/common';
import { ReactiveFormsModule } from '@angular/forms';
import { LoginPageComponent } from './pages/login-page/login-page.component';
import { ProgressSpinnerModule } from 'primeng/progressspinner';


@NgModule({
    declarations: [AppComponent],
    imports: [
        BrowserModule,
        AppRoutingModule,
        RouterModule,
        CommonModule,
        ReactiveFormsModule,
        ProgressSpinnerModule,
        SearchComponent,
        HeaderComponent,
        SerachSectionComponent,
        PodcastGridComponent,
        PodcastCardComponent,
        TrendingSearchesComponent,
        LoginFormComponent,
        LandingPageComponent,
        LoginPageComponent,
    ],
    providers: [
        provideAnimationsAsync(),
        providePrimeNG({
            theme: {
                preset: Material
            }
        })
    ],
    bootstrap: [AppComponent]
})
export class AppModule { }

import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';

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


@NgModule({
  declarations: [
    AppComponent,
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
  imports: [
    BrowserModule,
    AppRoutingModule,
    RouterModule,
    CommonModule,
    ReactiveFormsModule,
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }

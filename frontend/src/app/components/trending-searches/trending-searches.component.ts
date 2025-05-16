import { Component } from '@angular/core';

@Component({
    selector: 'app-trending-searches',
    templateUrl: './trending-searches.component.html',
    styles: ``
})
export class TrendingSearchesComponent {

  trendingItems: string[] = [
    "Moonlight Sonata",
    "The Beatles",
    "Adele",
    "Bach",
    "Rihanna",
    "Smooth Jazz",
    "Kanye West",
    "Ariana Grande",
    "Mozart",
    "Billie Eilish",
  ]

}

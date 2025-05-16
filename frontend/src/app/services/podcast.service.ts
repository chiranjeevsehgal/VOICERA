import { Injectable } from "@angular/core"
// import type { Podcast } from "../models/podcast.model"

@Injectable({
  providedIn: "root",
})
export class PodcastService {
  private podcasts: any[] = [
    {
      id: "1",
      title: "The Daily",
      creator: "The New York Times",
      imageUrl: "https://via.placeholder.com/300",
    },
    {
      id: "2",
      title: "Stuff You Should Know",
      creator: "iHR",
      imageUrl: "https://via.placeholder.com/300",
    },
    {
      id: "3",
      title: "TED Radio Hour",
      creator: "NPR",
      imageUrl: "https://via.placeholder.com/300",
    },
    {
      id: "4",
      title: "How I Built This",
      creator: "NPR",
      imageUrl: "https://via.placeholder.com/300",
    },
    {
      id: "5",
      title: "Wait Wait... Don't Tell Me!",
      creator: "NPR",
      imageUrl: "https://via.placeholder.com/300",
    },
    {
      id: "6",
      title: "The Joe Rogan Experience",
      creator: "Joe Rogan",
      imageUrl: "https://via.placeholder.com/300",
    },
    {
      id: "7",
      title: "Radiolab",
      creator: "WNYC Studios",
      imageUrl: "https://via.placeholder.com/300",
    },
    {
      id: "8",
      title: "Planet Money",
      creator: "NPR",
      imageUrl: "https://via.placeholder.com/300",
    },
    {
      id: "9",
      title: "The Dave Ramsey Show",
      creator: "Ramsey Solutions",
      imageUrl: "https://via.placeholder.com/300",
    },
    {
      id: "10",
      title: "Freakonomics Radio",
      creator: "Freakonomics Radio",
      imageUrl: "https://via.placeholder.com/300",
    },
  ]

  getPodcasts(): any[] {
    return this.podcasts
  }
}

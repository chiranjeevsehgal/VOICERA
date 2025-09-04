import {
  Component,
  OnInit,
  OnDestroy,
  AfterViewInit,
  ElementRef,
  ViewChild,
  NgZone,
} from '@angular/core';
import {
  debounceTime,
  distinctUntilChanged,
  Subject,
  Subscription,
} from 'rxjs';
import { Podcast, PodcastService } from '../../services/podcast.service';
import { HeaderComponent } from '../../components/header/header.component';
import { SerachSectionComponent } from '../../components/search-section/search-section.component';
import { PodcastGridComponent } from '../../components/podcast-grid/podcast-grid.component';
import { MessageService } from 'primeng/api';
import { AudioModalComponent } from '../../components/audio-modal/audio-modal.component';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-search',
  templateUrl: './search.component.html',
  styles: ``,
  imports: [
    CommonModule,
    HeaderComponent,
    SerachSectionComponent,
    AudioModalComponent,
    PodcastGridComponent,
  ],
  providers: [MessageService],
})
export class SearchComponent implements OnInit, OnDestroy, AfterViewInit {
  podcasts: any[] = [];
  filteredPodcasts: Podcast[] = [];
  searchQuery: string = '';
  selectedPodcast: Podcast | null = null;
  isModalVisible = false;
  private subscription?: Subscription;
  private searchSubscription?: Subscription;
  isSearching = false;
  isLoading = true;
  hasSearched = false;
  page = 1;
  hasNext = true;
  loadingMore = false;
  private io?: IntersectionObserver;
  @ViewChild('infiniteAnchor') infiniteAnchor?: ElementRef;
  private searchSubject = new Subject<string>();

  constructor(
    private podcastService: PodcastService,
    private messageService: MessageService,
    private ngZone: NgZone
  ) {}

  ngOnInit(): void {
    this.loadPodcasts();
    this.setupDebouncedSearch();
  }

  ngOnDestroy(): void {
    // Clean up subscription to prevent memory leaks
    if (this.subscription) {
      this.subscription.unsubscribe();
    }
    if (this.searchSubscription) {
      this.searchSubscription.unsubscribe();
    }
    this.searchSubject.complete();
    if (this.io) {
      this.io.disconnect();
    }
  }

  private setupDebouncedSearch(): void {
    this.searchSubscription = this.searchSubject
      .pipe(
        debounceTime(300), // Wait 300ms after user stops typing
        distinctUntilChanged() // Only emit if the value has changed
      )
      .subscribe((query: string) => {
        this.performSearch(query);
      });
  }

  private loadPodcasts(): void {
    this.loadPage(1);
  }

  ngAfterViewInit(): void {
    // Setup infinite scroll observer after view init
    if (this.infiniteAnchor) {
      this.setupInfiniteScroll();
    }
  }

  private setupInfiniteScroll(): void {
    if (this.io) this.io.disconnect();
    this.io = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (!entry || !entry.isIntersecting) return;
        if (this.isLoading || this.loadingMore || !this.hasNext) return;
        // Ensure updates happen inside Angular zone
        this.ngZone.run(() => this.loadNextPage());
      },
      {
        root: null,
        rootMargin: '200px',
        threshold: 0.1,
      }
    );
    if (this.infiniteAnchor?.nativeElement) {
      this.io.observe(this.infiniteAnchor.nativeElement);
    }
  }

  private loadPage(page: number): void {
    if (this.subscription) this.subscription.unsubscribe();
    if (page <= 1) {
      this.isLoading = true;
      this.page = 1;
      this.hasNext = true;
    } else {
      this.loadingMore = true;
    }

    this.subscription = this.podcastService.getPodcastsPage(page).subscribe({
      next: (res) => {
        if (page <= 1) {
          this.podcasts = res.podcasts;
        } else {
          this.podcasts = [...this.podcasts, ...res.podcasts];
        }
        this.page = res.page;
        this.hasNext = res.hasNext;
        this.filterPodcasts();
        this.isLoading = false;
        this.loadingMore = false;
      },
      error: (error) => {
        console.error('Error loading podcasts:', error);
        this.messageService.add({
          severity: 'error',
          summary: 'Error',
          detail: 'Failed to load podcasts',
        });
        this.isLoading = false;
        this.loadingMore = false;
      },
    });
  }

  private loadNextPage(): void {
    if (!this.hasNext || this.loadingMore) return;
    this.loadPage(this.page + 1);
  }

  onSearchChange(query: string): void {
    this.searchQuery = query.trim();
    this.searchSubject.next(this.searchQuery);
  }

  private performSearch(query: string): void {
    this.searchQuery = query;
    if (!this.searchQuery) {
      this.hasSearched = false;
    } else {
      this.hasSearched = true;
    }
    this.filterPodcasts();
  }

  onSearchSubmit(query: string): void {
    this.searchQuery = (query || '').trim();
    this.hasSearched = true;
    this.filterPodcasts();
  }

  private sortPodcastsByDate(podcasts: Podcast[]): Podcast[] {
    return podcasts.sort((a, b) => {
      // Assuming the podcast object has a date field like 'created_at', 'uploadDate', or 'audioFile.created_at'
      // Adjust the property path based on your actual data structure
      const dateA = new Date(a.audioFile?.created_at);
      const dateB = new Date(b.audioFile?.created_at);

      // Sort in descending order (newest first)
      return dateB.getTime() - dateA.getTime();
    });
  }

  private filterPodcasts(): void {
    if (!this.searchQuery) {
      this.filteredPodcasts = this.podcasts;
    } else {
      this.filteredPodcasts = this.podcasts.filter(
        (podcast) =>
          podcast.title
            .toLowerCase()
            .includes(this.searchQuery.toLowerCase()) ||
          podcast.creator.toLowerCase().includes(this.searchQuery.toLowerCase())
      );
    }
  }

  onPodcastCardClick(podcast: Podcast): void {
    this.selectedPodcast = podcast;
    this.isModalVisible = true;
  }

  onModalClose(): void {
    this.isModalVisible = false;
    this.selectedPodcast = null;
  }
}

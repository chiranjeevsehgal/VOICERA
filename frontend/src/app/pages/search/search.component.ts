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
import { PodcastListComponent } from '../../components/podcast-list/podcast-list.component';
import { AudioModalComponent } from '../../components/audio-modal/audio-modal.component';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HotToastService } from '@ngxpert/hot-toast';

@Component({
  selector: 'app-search',
  templateUrl: './search.component.html',
  styles: ``,
  imports: [
    CommonModule,
    FormsModule,
    HeaderComponent,
    SerachSectionComponent,
    AudioModalComponent,
    PodcastGridComponent,
    PodcastListComponent,
  ],
  providers: [],
})
export class SearchComponent implements OnInit, OnDestroy, AfterViewInit {
  podcasts: any[] = [];
  filteredPodcasts: Podcast[] = [];
  viewMode: 'grid' | 'list' = 'grid';
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
  // Backoff/Circuit Breaker state
  private backoffUntil: number | null = null;
  private backoffCurrentMs = 0;
  private readonly backoffBaseMs = 15000; // 15s initial wait
  private readonly backoffMaxMs = 120000; // cap at 2 minutes
  // Filters UI state
  showFilters: boolean = false;
  // Date filters
  dateQuick: 'today' | 'week' | 'month' | 'year' | null = null;
  dateCustomStart: string | null = null; // YYYY-MM-DD
  dateCustomEnd: string | null = null; // YYYY-MM-DD
  // Duration filters
  durationPreset: 'short' | 'medium' | 'long' | null = null;
  durationMin: number | null = null; // seconds
  durationMax: number | null = null; // seconds
  // Sorting
  sortBy:
    | 'newest'
    | 'oldest'
    | 'title_asc'
    | 'title_desc'
    | 'duration_asc'
    | 'duration_desc' = 'newest';

  constructor(
    private podcastService: PodcastService,
    private toast: HotToastService,
    private ngZone: NgZone,
  ) {}

  ngOnInit(): void {
    this.setDefaultViewMode();
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

  // ===== Backoff / Circuit Breaker helpers =====
  private startBackoff(): void {
    // Exponential backoff with cap
    this.backoffCurrentMs = this.backoffCurrentMs
      ? Math.min(this.backoffCurrentMs * 2, this.backoffMaxMs)
      : this.backoffBaseMs;
    this.backoffUntil = Date.now() + this.backoffCurrentMs;
  }

  private clearBackoff(): void {
    this.backoffUntil = null;
    this.backoffCurrentMs = 0;
  }

  isBackoffActive(): boolean {
    return this.backoffUntil !== null && Date.now() < this.backoffUntil;
  }

  getBackoffRemainingSeconds(): number {
    if (!this.isBackoffActive() || this.backoffUntil === null) return 0;
    return Math.max(0, Math.ceil((this.backoffUntil - Date.now()) / 1000));
  }

  retryNow(): void {
    // Allow manual retry and clear backoff window
    this.clearBackoff();
    // If nothing loaded yet, load first page; else reload current next state
    const targetPage = this.podcasts.length ? this.page : 1;
    this.loadPage(targetPage);
  }

  private setupDebouncedSearch(): void {
    this.searchSubscription = this.searchSubject
      .pipe(
        debounceTime(300), // Wait 300ms after user stops typing
        distinctUntilChanged(), // Only emit if the value has changed
      )
      .subscribe((query: string) => {
        this.performSearch(query);
      });
  }

  private loadPodcasts(): void {
    this.loadPage(1);
  }

  private setDefaultViewMode(): void {
    // Use Tailwind's sm breakpoint (640px) as the cutoff for mobile
    try {
      if (
        typeof window !== 'undefined' &&
        typeof window.matchMedia === 'function'
      ) {
        const isMobile = window.matchMedia('(max-width: 639px)').matches;
        this.viewMode = isMobile ? 'list' : 'grid';
      }
    } catch (e) {
      // Fallback: keep existing default if any error occurs
    }
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
        if (this.isBackoffActive()) return; // guard while backend is down
        // Ensure updates happen inside Angular zone
        this.ngZone.run(() => this.loadNextPage());
      },
      {
        root: null,
        rootMargin: '200px',
        threshold: 0.1,
      },
    );
    if (this.infiniteAnchor?.nativeElement) {
      this.io.observe(this.infiniteAnchor.nativeElement);
    }
  }

  private loadPage(page: number): void {
    // Do not attempt to load while in backoff window
    if (this.isBackoffActive()) {
      return;
    }
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
        // Success clears any previous backoff
        this.clearBackoff();
      },
      error: (error) => {
        console.error('Error loading podcasts:', error);
        // Start/extend backoff window to prevent repeated calls
        this.startBackoff();
        const seconds = this.getBackoffRemainingSeconds();
        this.toast.error(
          `Failed to load podcasts. Retrying disabled for ${seconds}s.`,
          { duration: 4000 },
        );
        this.isLoading = false;
        this.loadingMore = false;
      },
    });
  }

  private loadNextPage(): void {
    if (!this.hasNext || this.loadingMore) return;
    this.loadPage(this.page + 1);
  }

  setViewMode(mode: 'grid' | 'list'): void {
    this.viewMode = mode;
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
      const dateA = new Date(
        a.audioFile?.published_date || a.audioFile?.created_at,
      );
      const dateB = new Date(
        b.audioFile?.published_date || b.audioFile?.created_at,
      );

      // Sort in descending order (newest first)
      return dateB.getTime() - dateA.getTime();
    });
  }

  private filterPodcasts(): void {
    // Start with all podcasts
    let result: Podcast[] = this.podcasts;

    // Text search (title or creator)
    if (this.searchQuery) {
      const q = this.searchQuery.toLowerCase();
      result = result.filter(
        (p) =>
          p.title.toLowerCase().includes(q) ||
          p.creator.toLowerCase().includes(q),
      );
    }

    // Date filter (published_date preferred, fallback to created_at)
    const { start: dateStart, end: dateEnd } = this.computeDateRange();
    if (dateStart || dateEnd) {
      result = result.filter((p) => {
        const d = new Date(
          p.audioFile?.published_date || p.audioFile?.created_at,
        );
        if (isNaN(d.getTime())) return false;
        if (dateStart && d < dateStart) return false;
        if (dateEnd && d > dateEnd) return false;
        return true;
      });
    }

    // Duration filter (seconds)
    const durRange = this.computeDurationRange();
    if (durRange) {
      const { min, max } = durRange;
      result = result.filter((p) => {
        const dur = Number(p.audioFile?.duration_seconds ?? 0);
        if (min !== null && dur < min) return false;
        if (max !== null && dur > max) return false;
        return true;
      });
    }

    // Sorting
    result = this.sortResults(result);

    this.filteredPodcasts = result;
  }

  private sortResults(list: Podcast[]): Podcast[] {
    const arr = [...list];
    switch (this.sortBy) {
      case 'oldest':
        return arr.sort(
          (a, b) =>
            new Date(
              a.audioFile?.published_date || a.audioFile?.created_at,
            ).getTime() -
            new Date(
              b.audioFile?.published_date || b.audioFile?.created_at,
            ).getTime(),
        );
      case 'title_asc':
        return arr.sort((a, b) => a.title.localeCompare(b.title));
      case 'title_desc':
        return arr.sort((a, b) => b.title.localeCompare(a.title));
      case 'duration_asc':
        return arr.sort(
          (a, b) =>
            (a.audioFile?.duration_seconds ?? 0) -
            (b.audioFile?.duration_seconds ?? 0),
        );
      case 'duration_desc':
        return arr.sort(
          (a, b) =>
            (b.audioFile?.duration_seconds ?? 0) -
            (a.audioFile?.duration_seconds ?? 0),
        );
      case 'newest':
      default:
        return arr.sort(
          (a, b) =>
            new Date(
              b.audioFile?.published_date || b.audioFile?.created_at,
            ).getTime() -
            new Date(
              a.audioFile?.published_date || a.audioFile?.created_at,
            ).getTime(),
        );
    }
  }

  // Helpers: date range
  private computeDateRange(): { start: Date | null; end: Date | null } {
    const now = new Date();
    const endOfNow = new Date(now);
    // include the entire current day for quick ranges
    endOfNow.setHours(23, 59, 59, 999);

    let start: Date | null = null;
    let end: Date | null = null;

    if (this.dateQuick) {
      const startOfToday = new Date(now);
      startOfToday.setHours(0, 0, 0, 0);

      switch (this.dateQuick) {
        case 'today':
          start = startOfToday;
          end = endOfNow;
          break;
        case 'week':
          start = new Date(now);
          start.setDate(now.getDate() - 7);
          start.setHours(0, 0, 0, 0);
          end = endOfNow;
          break;
        case 'month':
          start = new Date(now.getFullYear(), now.getMonth(), 1);
          end = endOfNow;
          break;
        case 'year':
          start = new Date(now.getFullYear(), 0, 1);
          end = endOfNow;
          break;
      }
    } else if (this.dateCustomStart || this.dateCustomEnd) {
      if (this.dateCustomStart) {
        start = new Date(this.dateCustomStart + 'T00:00:00');
      }
      if (this.dateCustomEnd) {
        end = new Date(this.dateCustomEnd + 'T23:59:59');
      }
    }

    return { start, end };
  }

  // Helpers: duration range in seconds
  private computeDurationRange(): {
    min: number | null;
    max: number | null;
  } | null {
    if (this.durationPreset) {
      switch (this.durationPreset) {
        case 'short':
          return { min: 0, max: 60 };
        case 'medium':
          return { min: 60, max: 300 };
        case 'long':
          return { min: 300, max: null };
      }
    }
    if (this.durationMin !== null || this.durationMax !== null) {
      let min = this.durationMin !== null ? this.durationMin : null;
      let max = this.durationMax !== null ? this.durationMax : null;
      // Swap if user entered min > max
      if (min !== null && max !== null && min > max) {
        const tmp = min;
        min = max;
        max = tmp;
      }
      return { min, max };
    }
    return null;
  }

  // UI handlers
  toggleFilters(): void {
    this.showFilters = !this.showFilters;
  }

  setSort(sort: typeof this.sortBy): void {
    this.sortBy = sort;
    this.filterPodcasts();
  }

  setDateQuick(option: 'today' | 'week' | 'month' | 'year' | null): void {
    this.dateQuick = option;
    if (option) {
      // Clear custom when quick is set
      this.dateCustomStart = null;
      this.dateCustomEnd = null;
    }
    this.filterPodcasts();
  }

  onDateCustomChange(): void {
    // When custom date is set, clear quick option
    this.dateQuick = null;
    this.filterPodcasts();
  }

  setDurationPreset(preset: 'short' | 'medium' | 'long' | null): void {
    this.durationPreset = preset;
    if (preset) {
      this.durationMin = null;
      this.durationMax = null;
    }
    this.filterPodcasts();
  }

  onDurationCustomChange(): void {
    // Clear preset when custom values are edited
    this.durationPreset = null;
    this.filterPodcasts();
  }

  resetFilters(): void {
    this.dateQuick = null;
    this.dateCustomStart = null;
    this.dateCustomEnd = null;
    this.durationPreset = null;
    this.durationMin = null;
    this.durationMax = null;
    this.sortBy = 'newest';
    this.filterPodcasts();
  }

  get appliedFiltersCount(): number {
    let count = 0;
    if (this.dateQuick || this.dateCustomStart || this.dateCustomEnd)
      count += 1;
    if (
      this.durationPreset ||
      this.durationMin !== null ||
      this.durationMax !== null
    )
      count += 1;
    return count;
  }

  getAppliedFilterChips(): { key: 'date' | 'duration'; label: string }[] {
    const chips: { key: 'date' | 'duration'; label: string }[] = [];
    // Date
    if (this.dateQuick || this.dateCustomStart || this.dateCustomEnd) {
      let label = 'Date: ';
      if (this.dateQuick) {
        const map: any = {
          today: 'Today',
          week: 'This Week',
          month: 'This Month',
          year: 'This Year',
        };
        label += map[this.dateQuick];
      } else {
        const s = this.dateCustomStart || '—';
        const e = this.dateCustomEnd || '—';
        label += `${s} → ${e}`;
      }
      chips.push({ key: 'date', label });
    }
    // Duration
    if (
      this.durationPreset ||
      this.durationMin !== null ||
      this.durationMax !== null
    ) {
      let label = 'Duration: ';
      if (this.durationPreset) {
        if (this.durationPreset === 'short') label += 'Short (0–60s)';
        if (this.durationPreset === 'medium') label += 'Medium (60–300s)';
        if (this.durationPreset === 'long') label += 'Long (300s+)';
      } else {
        const min = this.durationMin !== null ? `${this.durationMin}s` : '0s';
        const max = this.durationMax !== null ? `${this.durationMax}s` : '∞';
        label += `${min} – ${max}`;
      }
      chips.push({ key: 'duration', label });
    }
    return chips;
  }

  removeFilter(key: 'date' | 'duration'): void {
    if (key === 'date') {
      this.dateQuick = null;
      this.dateCustomStart = null;
      this.dateCustomEnd = null;
    } else if (key === 'duration') {
      this.durationPreset = null;
      this.durationMin = null;
      this.durationMax = null;
    }
    this.filterPodcasts();
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

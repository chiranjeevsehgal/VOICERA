import { Component, OnInit, OnDestroy, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { HeaderComponent } from '../../components/header/header.component';
import { MessageService } from 'primeng/api';
import { FormsModule } from '@angular/forms';
import { Toast } from 'primeng/toast';
import { SemanticSearchService, SearchResult } from '../../services/semantic-search.service';

export interface SemanticPodcastGroup {
  id: string;
  title: string;
  creator: string;
  imageUrl: string;
  file_url: string;
  segments: SearchResult[];
}

@Component({
  selector: 'app-semantic-search',
  imports: [Toast, CommonModule, FormsModule, HeaderComponent],
  providers: [MessageService],
  templateUrl: './semantic-search.component.html',
  styles: ``
})
export class SemanticSearchComponent implements OnInit, OnDestroy {
  searchQuery: string = '';
  limit: number = 3;
  limits: number[] = Array.from({ length: 10 }, (_, i) => i + 1);
  minConfidence: number = 0.7;
  minRelevance: number = 0.65;
  confidenceOptions: number[] = [0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9];
  relevanceOptions: number[] = [0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9];
  // Flattened results for counts/stats
  searchResults: SearchResult[] = [];
  // Grouped by audio file
  groupedResults: SemanticPodcastGroup[] = [];
  loading = false;
  hasSearched = false;
  selectedGroup: SemanticPodcastGroup | null = null;
  currentSegmentIndex: number = 0;
  private subscription?: Subscription;
  @ViewChild('player') audioRef?: ElementRef<HTMLAudioElement>;

  constructor(
    private semanticSearchService: SemanticSearchService,
    private messageService: MessageService
  ) {}

  ngOnInit(): void {}

  ngOnDestroy(): void {
    if (this.subscription) {
      this.subscription.unsubscribe();
    }
  }

  onSearchInput(): void {
    // Optional: Add debouncing here if you want real-time search
  }

  onSearchSubmit(): void {
    if (this.searchQuery.trim()) {
      this.performSearch(this.searchQuery.trim());
    }
  }

  onSearchClear(): void {
    this.searchQuery = '';
    this.searchResults = [];
    this.hasSearched = false;
  }

  private performSearch(query: string): void {
    this.loading = true;
    this.hasSearched = false;
    
    this.subscription = this.semanticSearchService
      .searchAudio(query, this.limit, this.minConfidence, this.minRelevance)
      .subscribe({
      next: (response) => {
        // Keep flattened for counts
        this.searchResults = response.results;
        // Group by audio file for UI
        this.groupedResults = this.transformAndGroupResults(response.results);
        
        this.loading = false;
        this.hasSearched = true;
      },
      error: (error) => {
        console.error('Search error:', error);
        this.loading = false;
        this.hasSearched = true;
        this.messageService.add({
          severity: 'error',
          summary: 'Search Error',
          detail: 'Failed to perform search. Please try again.'
        });
      }
    });
  }

  private transformAndGroupResults(results: SearchResult[]): SemanticPodcastGroup[] {
    const groups = new Map<string, SearchResult[]>();
    for (const r of results) {
      const key = r.file_url || r.file_name;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(r);
    }

    const grouped: SemanticPodcastGroup[] = [];
    let idx = 0;
    groups.forEach((segments, key) => {
      // Sort segments by combined_score desc (fallback to semantic_score)
      segments.sort((a, b) => (b.combined_score ?? b.semantic_score ?? 0) - (a.combined_score ?? a.semantic_score ?? 0));
      const first = segments[0];
      grouped.push({
        id: `group-${idx++}`,
        title: this.extractTitleFromFilename(first.file_name),
        creator: 'AI Search Result',
        imageUrl: 'https://developers.elementor.com/docs/assets/img/elementor-placeholder-image.png',
        file_url: first.file_url,
        segments,
      });
    });

    return grouped;
  }

  private extractTitleFromFilename(filename: string): string {
    return filename.replace('.mp3', '').replace(/[-_]/g, ' ');
  }

  onGroupCardClick(group: SemanticPodcastGroup): void {
    this.selectedGroup = group;
    this.currentSegmentIndex = 0;
    // Defer to allow modal to render and #player to be available
    setTimeout(() => this.seekToCurrentSegment(), 0);
  }

  onModalClose(): void {
    this.selectedGroup = null;
    this.currentSegmentIndex = 0;
  }

  nextSegment(): void {
    if (!this.selectedGroup) return;
    const n = this.selectedGroup.segments.length;
    this.currentSegmentIndex = (this.currentSegmentIndex + 1) % n;
    this.seekToCurrentSegment();
  }

  prevSegment(): void {
    if (!this.selectedGroup) return;
    const n = this.selectedGroup.segments.length;
    this.currentSegmentIndex = (this.currentSegmentIndex - 1 + n) % n;
    this.seekToCurrentSegment();
  }

  formatTime(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  get currentSegment(): SearchResult | null {
    if (!this.selectedGroup) return null;
    return this.selectedGroup.segments[this.currentSegmentIndex] ?? null;
  }

  onAudioLoaded(): void {
    this.seekToCurrentSegment();
  }

  private seekToCurrentSegment(): void {
    const seg = this.currentSegment;
    const el = this.audioRef?.nativeElement;
    if (seg && el) {
      try {
        el.currentTime = Math.max(0, seg.start_time);
      } catch {
        // ignore
      }
    }
  }
}
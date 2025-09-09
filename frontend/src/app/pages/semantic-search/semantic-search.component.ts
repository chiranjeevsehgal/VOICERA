import {
  Component,
  OnInit,
  OnDestroy,
  ElementRef,
  ViewChild,
  AfterViewInit,
} from '@angular/core';
import { Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { Subscription } from 'rxjs';
import { HeaderComponent } from '../../components/header/header.component';
import { FormsModule } from '@angular/forms';
import {
  SemanticSearchService,
  SearchResult,
} from '../../services/semantic-search.service';
import { HotToastService } from '@ngxpert/hot-toast';

export interface SemanticPodcastGroup {
  id: string;
  title: string;
  creator: string;
  imageUrl: string;
  file_url: string;
  segments: SearchResult[];
}

// Removed perceptron animation classes (replaced by CSS spinner orbits)

@Component({
  selector: 'app-semantic-search',
  imports: [CommonModule, FormsModule, HeaderComponent],
  providers: [],
  templateUrl: './semantic-search.component.html',
  styles: `
    /* Branded Loader (VOICERA) */
    :host {
      --brand-primary: #6366f1; /* indigo-500 */
      --brand-secondary: #a855f7; /* purple-500 */
      --brand-accent: #22d3ee; /* cyan-400 */
      --ring-track: rgba(99, 102, 241, 0.15);
      --glow-1: rgba(99, 102, 241, 0.45);
      --glow-2: rgba(168, 85, 247, 0.25);
    }

    @keyframes spin {
      from {
        transform: rotate(0deg);
      }
      to {
        transform: rotate(360deg);
      }
    }

    @keyframes spinReverse {
      from {
        transform: rotate(0deg);
      }
      to {
        transform: rotate(-360deg);
      }
    }

    @keyframes dash {
      0% {
        stroke-dashoffset: 300;
      }
      50% {
        stroke-dashoffset: 140;
      }
      100% {
        stroke-dashoffset: 300;
      }
    }

    @keyframes pulse {
      0%,
      100% {
        transform: translate(-50%, -50%) scale(1);
      }
      50% {
        transform: translate(-50%, -50%) scale(1.06);
      }
    }

    .brand-loader {
      position: relative;
      width: 168px;
      height: 168px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      isolation: isolate;
      filter: drop-shadow(0 4px 18px rgba(2, 8, 23, 0.08))
        drop-shadow(0 8px 32px rgba(99, 102, 241, 0.15));
    }

    .brand-ring {
      position: absolute;
      inset: 0;
      transform-origin: 50% 50%;
    }

    .brand-ring--outer {
      animation: spin 1.8s linear infinite;
    }

    .brand-ring--inner {
      inset: 20px;
      animation: spinReverse 1.4s linear infinite;
    }

    .brand-ring .track {
      fill: none;
      stroke: var(--ring-track);
      stroke-width: 8;
    }

    .brand-ring .indicator {
      fill: none;
      stroke-width: 8;
      stroke-linecap: round;
      stroke-dasharray: 220;
      stroke-dashoffset: 300;
      animation: dash 1.8s ease-in-out infinite;
    }

    .brand-ring--inner .indicator {
      stroke-dasharray: 160;
      animation-duration: 1.4s;
    }

    .brand-loader__core {
      position: absolute;
      left: 50%;
      top: 50%;
      width: 38px;
      height: 38px;
      border-radius: 999px;
      transform: translate(-50%, -50%);
      background:
        radial-gradient(
          40% 40% at 30% 30%,
          #ffffff 0%,
          #ffffff 30%,
          rgba(255, 255, 255, 0.75) 60%,
          rgba(255, 255, 255, 0) 100%
        ),
        radial-gradient(
          100% 100% at 50% 50%,
          rgba(99, 102, 241, 0.25) 0%,
          rgba(99, 102, 241, 0) 60%
        );
      box-shadow:
        0 0 22px var(--glow-1),
        0 0 38px var(--glow-2);
      border: 1px solid rgba(255, 255, 255, 0.65);
      animation: pulse 1.8s ease-in-out infinite;
      backdrop-filter: blur(2px);
    }
  `,
})
export class SemanticSearchComponent
  implements OnInit, OnDestroy, AfterViewInit
{
  searchQuery: string = '';
  limit: number = 3;
  limits: number[] = Array.from({ length: 10 }, (_, i) => i + 1);
  minConfidence: number = 0.4;
  minRelevance: number = 0.055;
  validateContent: boolean = false;
  confidenceOptions: number[] = [
    0.0, 0.1, 0.2, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85,
    0.9, 0.95,
  ];
  relevanceOptions: number[] = [
    0.0, 0.1, 0.2, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85,
    0.9, 0.95,
  ];
  // Flattened results for counts/stats
  searchResults: SearchResult[] = [];
  // Grouped by audio file
  groupedResults: SemanticPodcastGroup[] = [];
  loading = false;
  hasSearched = false;
  showAdvanced = false;
  selectedGroup: SemanticPodcastGroup | null = null;
  currentSegmentIndex: number = 0;
  private subscription?: Subscription;
  @ViewChild('player') audioRef?: ElementRef<HTMLAudioElement>;

  // Removed perceptron canvas references and properties

  constructor(
    private semanticSearchService: SemanticSearchService,
    private router: Router,
    private toast: HotToastService,
  ) {}

  ngOnInit(): void {}

  ngAfterViewInit(): void {
    // Perceptron animation disabled; spinner orbits are CSS-based
  }

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

  toggleAdvanced(): void {
    this.showAdvanced = !this.showAdvanced;
  }

  private performSearch(query: string): void {
    this.loading = true;
    this.hasSearched = false;

    this.subscription = this.semanticSearchService
      .searchAudio(
        query,
        this.limit,
        this.minConfidence,
        this.minRelevance,
        this.validateContent,
      )
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
          this.toast.error('Failed to perform search. Please try again.');
        },
      });
  }

  private transformAndGroupResults(
    results: SearchResult[],
  ): SemanticPodcastGroup[] {
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
      segments.sort(
        (a, b) =>
          (b.combined_score ?? b.semantic_score ?? 0) -
          (a.combined_score ?? a.semantic_score ?? 0),
      );
      const first = segments[0];
      grouped.push({
        id: `group-${idx++}`,
        title: this.extractTitleFromFilename(first.file_name),
        creator: 'AI Search Result',
        imageUrl:
          'https://developers.elementor.com/docs/assets/img/elementor-placeholder-image.png',
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

  goToAiAnswer(group: SemanticPodcastGroup, event?: Event): void {
    // Prevent opening the modal when clicking the arrow icon
    if (event) {
      event.stopPropagation();
      event.preventDefault();
    }
    this.router.navigateByUrl('/ai-answer', {
      state: {
        searchQuery: this.searchQuery,
        fileUrl: group.file_url,
        title: group.title,
      },
    });
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

  get uniqueFilesCount(): number {
    const uniqueUrls = new Set(
      this.searchResults.map((r) => r.file_url || r.file_name),
    );
    return uniqueUrls.size;
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

  // CSS-based spinner orbits used during loading (no TS animation required)
}

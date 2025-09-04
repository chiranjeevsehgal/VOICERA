import { Component, OnInit, OnDestroy, ElementRef, ViewChild, AfterViewInit } from '@angular/core';
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

// Perceptron Animation Classes
class Perceptron {
  weights: number[];

  constructor() {
    this.weights = new Array(3);
    for (let i = 0, n = 3; i < n; i++) {
      this.weights[i] = (Math.random() * 2) - 1;
    }
  }

  feed(inputs: number[]): number {
    let sum = 0;
    for (let i = 0, len = this.weights.length; i < len; i++) {
      sum += inputs[i] * this.weights[i];
    }
    return this.activate(sum);
  }

  activate(sum: number): number {
    return (sum > 0) ? 1 : -1;
  }

  train(inputs: number[], desired: number): void {
    const c = 2;
    let guess = this.feed(inputs);
    let error = desired - guess;

    for (let i = 0, len = this.weights.length; i < len; i++) {
      this.weights[i] += parseInt((c * error * inputs[i]).toString());
    }
  }
}

class Trainer {
  inputs: number[];
  answer: number;

  constructor(x: number, y: number, a: number) {
    this.inputs = new Array(3);
    this.inputs[0] = x;
    this.inputs[1] = y;
    this.inputs[2] = 1;
    this.answer = a;
  }
}

@Component({
  selector: 'app-semantic-search',
  imports: [Toast, CommonModule, FormsModule, HeaderComponent],
  providers: [MessageService],
  templateUrl: './semantic-search.component.html',
  styles: ``
})
export class SemanticSearchComponent implements OnInit, OnDestroy, AfterViewInit {
  searchQuery: string = '';
  limit: number = 10;
  limits: number[] = Array.from({ length: 10 }, (_, i) => i + 1);
  minConfidence: number = 0.2;
  minRelevance: number = 0.2;
  confidenceOptions: number[] = [0.0, 0.2, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9];
  relevanceOptions: number[] = [0.0, 0.2, 0.4, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9];
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
  @ViewChild('perceptronCanvas') canvasRef?: ElementRef<HTMLCanvasElement>;

  // Perceptron animation properties
  private perceptron?: Perceptron;
  private trainers: Trainer[] = [];
  private currentTrainer = 0;
  private animationId?: number;
  private readonly NUM_POINTS = 2000;
  private readonly COLOR_POS = '#4f46e5'; // indigo-600
  private readonly COLOR_NEG = '#e5e7eb'; // gray-200

  constructor(
    private semanticSearchService: SemanticSearchService,
    private messageService: MessageService
  ) {}

  ngOnInit(): void {}

  ngAfterViewInit(): void {
    // Initialize perceptron animation when canvas is available
    if (this.loading) {
      this.initPerceptronAnimation();
    }
  }

  ngOnDestroy(): void {
    if (this.subscription) {
      this.subscription.unsubscribe();
    }
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
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
    
    // Start perceptron animation
    setTimeout(() => this.initPerceptronAnimation(), 100);
    
    this.subscription = this.semanticSearchService
      .searchAudio(query, this.limit, this.minConfidence, this.minRelevance)
      .subscribe({
      next: (response) => {
        // Keep flattened for counts
        this.searchResults = response.results;
        // Group by audio file for UI
        this.groupedResults = this.transformAndGroupResults(response.results);
        
        this.stopPerceptronAnimation();
        this.loading = false;
        this.hasSearched = true;
      },
      error: (error) => {
        console.error('Search error:', error);
        this.stopPerceptronAnimation();
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

  // Perceptron Animation Methods
  private initPerceptronAnimation(): void {
    const canvas = this.canvasRef?.nativeElement;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Set canvas size
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height;

    // Initialize perceptron and trainers
    this.perceptron = new Perceptron();
    this.trainers = [];
    this.currentTrainer = 0;

    // Create training data
    for (let i = 0; i < this.NUM_POINTS; i++) {
      const x = Math.floor(Math.random() * canvas.width);
      const y = Math.floor(Math.random() * canvas.height);
      const answer = (y > (canvas.height / canvas.width) * x) ? 1 : -1;
      this.trainers[i] = new Trainer(x, y, answer);
    }

    // Clear canvas
    ctx.fillStyle = '#f8fafc'; // slate-50
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Start animation
    this.animatePerceptron();
  }

  private animatePerceptron(): void {
    const canvas = this.canvasRef?.nativeElement;
    if (!canvas || !this.perceptron) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Train perceptron with current trainer
    if (this.currentTrainer < this.trainers.length) {
      this.perceptron.train(
        this.trainers[this.currentTrainer].inputs,
        this.trainers[this.currentTrainer].answer
      );

      // Draw points up to current trainer
      for (let i = 0; i < this.currentTrainer; i++) {
        ctx.beginPath();
        ctx.arc(
          this.trainers[i].inputs[0],
          this.trainers[i].inputs[1],
          3,
          0,
          2 * Math.PI,
          false
        );
        ctx.fillStyle = (this.perceptron.feed(this.trainers[i].inputs) > 0) 
          ? this.COLOR_POS 
          : this.COLOR_NEG;
        ctx.fill();
      }

      this.currentTrainer++;
      
      // Continue animation if loading and not finished
      if (this.loading && this.currentTrainer < this.NUM_POINTS) {
        this.animationId = requestAnimationFrame(() => this.animatePerceptron());
      }
    }
  }

  private stopPerceptronAnimation(): void {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = undefined;
    }
  }
}
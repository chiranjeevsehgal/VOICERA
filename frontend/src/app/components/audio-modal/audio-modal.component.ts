import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnInit,
  OnDestroy,
  ElementRef,
  ViewChild,
  OnChanges,
  SimpleChanges,
  ViewChildren,
  QueryList,
  AfterViewInit,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  Podcast,
  PodcastService,
  WordTiming,
} from '../../services/podcast.service';
import { take } from 'rxjs';

@Component({
  selector: 'app-audio-modal',
  imports: [CommonModule],
  templateUrl: './audio-modal.component.html',
  styles: `
    .word-chip {
      transition:
        box-shadow 120ms ease,
        background-color 120ms ease,
        color 120ms ease;
    }
    .word-chip.active {
      box-shadow: 0 0 0.45rem rgba(99, 102, 241, 0.55);
      animation: word-glow 1.1s ease-in-out infinite alternate;
    }
    @keyframes word-glow {
      from {
        box-shadow: 0 0 0.25rem rgba(99, 102, 241, 0.35);
      }
      to {
        box-shadow: 0 0 0.7rem rgba(99, 102, 241, 0.65);
      }
    }
  `,
})
export class AudioModalComponent
  implements OnInit, OnDestroy, OnChanges, AfterViewInit
{
  @Input() podcast: Podcast | null = null;
  @Input() isVisible = false;
  @Output() close = new EventEmitter<void>();
  @ViewChild('audioPlayer') audioPlayer!: ElementRef<HTMLAudioElement>;
  @ViewChild('transcriptScroll') transcriptScroll!: ElementRef<HTMLDivElement>;
  @ViewChildren('wordEl') wordEls!: QueryList<ElementRef<HTMLElement>>;

  duration = 0;
  currentTime = 0;
  isPlaying = false;

  // Transcript state
  transcript: string | null = null;
  transcriptLoading = false;
  transcriptError: string | null = null;
  words: WordTiming[] = [];
  activeWordIndex = -1;

  private scrollScheduled = false;
  private rafId: number | null = null;

  constructor(private podcastService: PodcastService) {}

  ngOnInit() {
    if (this.isVisible) {
      document.body.style.overflow = 'hidden';
    }
  }

  ngAfterViewInit(): void {
    // When the rendered word list changes, re-evaluate scroll position
    if (this.wordEls) {
      this.wordEls.changes.subscribe(() => this.scheduleScrollToActive());
    }
  }

  ngOnDestroy() {
    document.body.style.overflow = 'auto';
    if (this.rafId != null) {
      cancelAnimationFrame(this.rafId);
      this.rafId = null;
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    const becameVisible =
      changes['isVisible']?.currentValue === true &&
      changes['isVisible']?.previousValue !== true;
    const podcastChanged = !!changes['podcast'];

    // Prefill duration from API if available (fallback to loaded metadata later)
    if (podcastChanged) {
      this.duration = this.podcast?.audioFile?.duration_seconds ?? 0;
    }

    if ((becameVisible || podcastChanged) && this.isVisible) {
      this.fetchTranscript();
    }
  }

  onBackdropClick(event: MouseEvent) {
    if (event.target === event.currentTarget) {
      this.closeModal();
    }
  }

  closeModal() {
    this.isVisible = false;
    document.body.style.overflow = 'auto';
    if (this.audioPlayer?.nativeElement) {
      this.audioPlayer.nativeElement.pause();
    }
    this.close.emit();
  }

  onTimeUpdate() {
    if (this.audioPlayer?.nativeElement) {
      this.currentTime = this.audioPlayer.nativeElement.currentTime;
      if (this.words && this.words.length > 0) {
        const idx = this.findActiveWordIndex(this.currentTime);
        if (idx !== this.activeWordIndex) {
          this.activeWordIndex = idx;
          this.scheduleScrollToActive();
        }
      }
    }
  }

  onLoadedMetadata() {
    if (this.audioPlayer?.nativeElement) {

      this.duration = this.audioPlayer.nativeElement.duration;
    }
  }

  private fetchTranscript() {
    // Reset state
    this.transcript = null;
    this.transcriptError = null;
    this.words = [];

    const mp3Url =
      this.podcast?.audioFile?.embedded_audio_url ||
      this.podcast?.audioFile?.user_data?.file_url;
    if (!mp3Url) return;

    this.transcriptLoading = true;
    this.podcastService
      .extractTranscriptData(mp3Url)
      .pipe(take(1))
      .subscribe({
        next: (data) => {
          this.transcript = data?.transcript || '';
          this.words = Array.isArray(data?.words) ? data.words : [];
          this.transcriptLoading = false;
          // After words load, ensure initial scroll to the first/active word
          this.activeWordIndex = this.findActiveWordIndex(this.currentTime);
          this.scheduleScrollToActive();
        },
        error: (err) => {
          this.transcriptError =
            err?.error?.detail || 'Failed to fetch transcript';
          this.transcriptLoading = false;
        },
      });
  }

  isWordActive(w: WordTiming): boolean {
    const t = this.currentTime;
    return (
      typeof w?.start === 'number' &&
      typeof w?.end === 'number' &&
      t >= w.start &&
      t <= w.end
    );
  }

  onWordClick(w: WordTiming) {
    const player = this.audioPlayer?.nativeElement;
    if (!player || typeof w?.start !== 'number') return;
    player.currentTime = Math.max(0, w.start);
    // keep current play/pause state
  }

  private findActiveWordIndex(t: number): number {
    if (!this.words || this.words.length === 0) return -1;
    for (let i = 0; i < this.words.length; i++) {
      const w = this.words[i];
      if (
        typeof w.start === 'number' &&
        typeof w.end === 'number' &&
        t >= w.start &&
        t <= w.end
      ) {
        return i;
      }
    }
    return -1;
  }

  private scheduleScrollToActive() {
    if (this.scrollScheduled) return;
    this.scrollScheduled = true;
    this.rafId = requestAnimationFrame(() => {
      this.scrollScheduled = false;
      this.scrollActiveWordIntoView();
    });
  }

  private scrollActiveWordIntoView() {
    if (this.activeWordIndex < 0) return;
    const container = this.transcriptScroll?.nativeElement;
    const el = this.wordEls?.get?.(this.activeWordIndex)?.nativeElement;
    if (!container || !el) return;

    // Smoothly bring the active word into view within the scroll container
    try {
      el.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
        inline: 'nearest',
      });
    } catch {
      // Fallback manual scroll
      const elTop = el.offsetTop;
      const elBottom = elTop + el.offsetHeight;
      const viewTop = container.scrollTop;
      const viewBottom = viewTop + container.clientHeight;
      if (elTop < viewTop) {
        container.scrollTo({
          top: elTop - container.clientHeight * 0.3,
          behavior: 'smooth',
        });
      } else if (elBottom > viewBottom) {
        container.scrollTo({
          top: elBottom - container.clientHeight * 0.7,
          behavior: 'smooth',
        });
      }
    }
  }

  formatTime(seconds: number): string {
    if (!seconds || isNaN(seconds)) return '0:00';

    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';

    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  formatDate(dateString: string): string {
    return new Date(dateString).toLocaleDateString();
  }
}

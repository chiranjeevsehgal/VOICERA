import {
  Component,
  ElementRef,
  EventEmitter,
  Input,
  Output,
  ViewChild,
} from '@angular/core';
import { Podcast } from '../../services/podcast.service';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-podcast-card',
  imports: [CommonModule],
  templateUrl: './podcast-card.component.html',
  styles: ``,
})
export class PodcastCardComponent {
  @Input() podcast!: any;
  @Output() cardClick = new EventEmitter<Podcast>();
  @ViewChild('audioPlayer') audioPlayer!: ElementRef<HTMLAudioElement>;

  onCardClick() {
    this.cardClick.emit(this.podcast);
  }

  formatTime(seconds: number): string {
    if (!seconds || isNaN(seconds)) return '0:00';

    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }
}

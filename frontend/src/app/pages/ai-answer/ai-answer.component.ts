import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HeaderComponent } from '../../components/header/header.component';
import { Router } from '@angular/router';
import { SemanticSearchService } from '../../services/semantic-search.service';
import { PodcastService } from '../../services/podcast.service';

interface SearchAndAnswerPayload {
  search_query: string;
  result_id: string;
  transcript: string;
}

@Component({
  selector: 'app-ai-answer',
  standalone: true,
  imports: [CommonModule, HeaderComponent],
  templateUrl: './ai-answer.component.html',
})
export class AiAnswerComponent implements OnInit {
  // Incoming state
  searchQuery: string = '';
  fileUrl: string = '';
  title: string = '';

  // UI state
  loadingTranscript = true;
  loadingAnswer = true;
  error?: string;

  // Results
  transcript: string = '';
  answer?: { result_id: string; search_query: string; answer: string; model?: string };

  constructor(
    private router: Router,
    private semanticService: SemanticSearchService,
    private podcastService: PodcastService,
  ) {}

  ngOnInit(): void {
    const nav = this.router.getCurrentNavigation();
    const state = nav?.extras?.state || (history?.state ?? {});

    this.searchQuery = state?.searchQuery || '';
    this.fileUrl = state?.fileUrl || '';
    this.title = state?.title || '';

    if (!this.searchQuery || !this.fileUrl) {
      this.error = 'Missing search context. Please go back and select a result again.';
      this.loadingTranscript = false;
      this.loadingAnswer = false;
      return;
    }

    // 1) Fetch transcript for the selected audio file
    this.podcastService.extractTranscript(this.fileUrl).subscribe({
      next: (transcript) => {
        this.transcript = transcript || '';
        this.loadingTranscript = false;
        // 2) Call search-and-answer with the transcript
        const payload: SearchAndAnswerPayload = {
          search_query: this.searchQuery,
          result_id: `req_${Date.now()}`,
          transcript: this.transcript,
        };
        this.semanticService.searchAndAnswer(payload).subscribe({
          next: (res) => {
            this.answer = res;
            this.loadingAnswer = false;
          },
          error: (err) => {
            console.error('search-and-answer error', err);
            this.error = 'Failed to fetch AI answer. Please try again.';
            this.loadingAnswer = false;
          },
        });
      },
      error: (err) => {
        console.error('transcript fetch error', err);
        this.error = 'Failed to fetch transcript for the selected audio.';
        this.loadingTranscript = false;
        this.loadingAnswer = false;
      },
    });
  }
}

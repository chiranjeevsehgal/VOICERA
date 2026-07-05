import { Component, OnInit, ViewChild, ElementRef } from '@angular/core';

import { HeaderComponent } from '../../components/header/header.component';
import { Router } from '@angular/router';
import { SemanticSearchService } from '../../services/semantic-search.service';
import { PodcastService } from '../../services/podcast.service';
import { FormsModule } from '@angular/forms';

type ChatRole = 'user' | 'assistant' | 'system';
interface ChatMessage {
  role: ChatRole;
  content: string;
}

@Component({
  selector: 'app-ai-answer',
  standalone: true,
  imports: [HeaderComponent, FormsModule],
  templateUrl: './ai-answer.component.html',
})
export class AiAnswerComponent implements OnInit {
  // Incoming state
  searchQuery: string = '';
  fileUrl: string = '';
  title: string = '';

  // UI state
  loadingTranscript = true;
  loadingAnswer = false;
  error?: string;

  // Results
  transcript: string = '';
  answer?: {
    result_id: string;
    search_query: string;
    answer: string;
    model?: string;
  };

  // Chat state
  messages: ChatMessage[] = [];
  userInput: string = '';
  sending: boolean = false;

  @ViewChild('scrollContainer')
  private scrollContainer?: ElementRef<HTMLDivElement>;

  constructor(
    private router: Router,
    private semanticService: SemanticSearchService,
    private podcastService: PodcastService,
  ) {}

  ngOnInit(): void {
    const nav = this.router.currentNavigation();
    const state = nav?.extras?.state || (history?.state ?? {});

    this.searchQuery = state?.searchQuery || '';
    this.fileUrl = state?.fileUrl || '';
    this.title = state?.title || '';

    if (!this.fileUrl) {
      this.error =
        'Missing audio context. Please go back and select a result again.';
      this.loadingTranscript = false;
      this.loadingAnswer = false;
      return;
    }

    // 1) Fetch transcript for the selected audio file
    this.podcastService.extractTranscript(this.fileUrl).subscribe({
      next: (transcript) => {
        this.transcript = transcript || '';
        this.loadingTranscript = false;
        // Seed system context and send the initial query automatically
        this.seedSystemContext();
        if (this.searchQuery?.trim()) {
          this.pushUserAndSend(this.searchQuery.trim());
        }
      },
      error: (err) => {
        console.error('transcript fetch error', err);
        this.error = 'Failed to fetch transcript for the selected audio.';
        this.loadingTranscript = false;
        this.loadingAnswer = false;
      },
    });
  }

  seedSystemContext(): void {
    const intro: string[] = [];
    if (this.title)
      intro.push(`You are helping with content from: "${this.title}".`);
    intro.push(
      'Answer based strictly on the transcript context and prior messages. If unsure, say you are not sure.',
    );
    this.messages.push({ role: 'system', content: intro.join(' ') });
    this.scrollToBottom();
  }

  send(): void {
    const prompt = (this.userInput || '').trim();
    if (!prompt || this.sending || this.loadingTranscript) return;
    this.userInput = '';
    this.pushUserAndSend(prompt);
  }

  onEnterKey(event: Event): void {
    // Submit on Enter from textarea and prevent inserting a newline
    this.send();
    event.preventDefault();
  }

  private pushUserAndSend(prompt: string): void {
    this.messages.push({ role: 'user', content: prompt });
    this.scrollToBottom();
    this.dispatchToBackend(prompt);
  }

  private dispatchToBackend(prompt: string): void {
    this.sending = true;
    this.loadingAnswer = true;

    const payload: any = {
      search_query: prompt,
      result_id: `req_${Date.now()}`,
      transcript: this.transcript,
      history: this.messages.map((m) => ({ role: m.role, content: m.content })),
      context: this.title || undefined,
    };

    this.semanticService.searchAndAnswer(payload).subscribe({
      next: (res) => {
        this.answer = res;
        const reply = (res?.answer ?? '').trim();
        this.messages.push({ role: 'assistant', content: reply || '...' });
        this.loadingAnswer = false;
        this.sending = false;
        this.scrollToBottom();
      },
      error: (err) => {
        console.error('search-and-answer error', err);
        this.error = 'Failed to fetch AI answer. Please try again.';
        this.messages.push({
          role: 'assistant',
          content: 'Sorry, I could not generate a response right now.',
        });
        this.loadingAnswer = false;
        this.sending = false;
        this.scrollToBottom();
      },
    });
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      const el = this.scrollContainer?.nativeElement;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    }, 0);
  }
}

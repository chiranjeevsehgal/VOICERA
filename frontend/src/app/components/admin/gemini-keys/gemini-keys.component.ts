import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import {
  GeminiKeysService,
  GeminiKeysStatusResponse,
  GeminiKeyStatusItem,
} from '../../../services/admin/gemini-keys.service';
import { shouldUseMockData } from '../../../utils/role.utils';
import * as mockGeminiKeysData from '../../../utils/mockData/mockKeys.json';

@Component({
  selector: 'app-gemini-keys',
  standalone: true,
  imports: [CommonModule, HttpClientModule, FormsModule],
  providers: [GeminiKeysService],
  templateUrl: './gemini-keys.component.html',
  styles: ``,
})
export class GeminiKeysComponent implements OnInit {
  loading = false;
  refreshing = false;
  error = '';

  data: GeminiKeysStatusResponse | null = null;

  // Gemini API error reference (aligned with Google documentation)
  geminiErrorDocs: Array<{
    http: number;
    status: string;
    description: string;
    solution: string;
    example?: string;
  }> = [
    {
      http: 400,
      status: 'INVALID_ARGUMENT',
      description:
        'The request body is malformed. There is a typo, or a missing required field in your request.',
      solution:
        'Check the API reference for request format, examples, and supported versions. Using features from a newer API version with an older endpoint can cause errors.',
      example:
        'E.g., missing required generationConfig field or invalid model parameter.',
    },
    {
      http: 400,
      status: 'FAILED_PRECONDITION',
      description:
        'Gemini API free tier is not available in your country. Billing not enabled for your project in Google AI Studio.',
      solution:
        'Enable billing on your project in Google AI Studio (set up a paid plan) or use a supported region.',
      example:
        'E.g., requests from unsupported region without billing enabled.',
    },
    {
      http: 403,
      status: 'PERMISSION_DENIED',
      description:
        "Your API key doesn't have the required permissions, or you're trying to use a tuned model without proper authentication.",
      solution:
        'Check that your API key is set and has the right access. Make sure to authenticate properly to use tuned models.',
      example: 'E.g., using a restricted key to access tuned model endpoints.',
    },
    {
      http: 404,
      status: 'NOT_FOUND',
      description:
        "The requested resource wasn't found (e.g., a referenced image, audio, or video file wasn't found).",
      solution:
        'Check if all parameters in your request are valid for your API version and that all referenced resources exist.',
      example: 'E.g., referencing a blob ID that does not exist.',
    },
    {
      http: 429,
      status: 'RESOURCE_EXHAUSTED',
      description:
        "You've exceeded the rate limit (too many requests per minute/quota).",
      solution:
        "Verify you're within the model's rate limits and consider requesting a quota increase. Implement retries with backoff.",
      example: 'E.g., free tier RPM exceeded.',
    },
    {
      http: 500,
      status: 'INTERNAL',
      description:
        "An unexpected error occurred on Google's side, or your input context might be too long.",
      solution:
        'Reduce your input context or temporarily switch to another model variant and retry. If persistent, report through Google AI Studio feedback.',
      example: 'E.g., context window overflow.',
    },
    {
      http: 503,
      status: 'UNAVAILABLE',
      description: 'The service may be temporarily overloaded or down.',
      solution:
        'Wait and retry, or temporarily switch to another model variant.',
      example: 'E.g., temporary service capacity issues.',
    },
    {
      http: 504,
      status: 'DEADLINE_EXCEEDED',
      description:
        'The service is unable to finish processing within the deadline (prompt/context too large).',
      solution:
        "Increase the client's timeout and/or reduce prompt/context size.",
      example: 'E.g., client timeout set too low for long prompt.',
    },
  ];

  constructor(private gemini: GeminiKeysService) {}

  ngOnInit(): void {
    this.loadStatus();
  }

  loadStatus(): void {
    if (!this.refreshing) {
      this.loading = true;
    }
    this.error = '';

    // Check if we should use mock data
    if (shouldUseMockData()) {
      // Mock data response with proper typing
      const mockResponse = mockGeminiKeysData as GeminiKeysStatusResponse;

      // Simulate API delay for realistic behavior
      setTimeout(() => {
        this.data = mockResponse;
        this.loading = false;
        this.refreshing = false;
      }, 500);

      return;
    }

    // Normal API call flow
    this.gemini.getStatus().subscribe({
      next: (resp) => {
        this.data = resp;
        this.loading = false;
        this.refreshing = false;
      },
      error: (err) => {
        console.error('Failed to load Gemini Keys status', err);
        this.error = 'Failed to load Gemini Keys status. Please try again.';
        this.loading = false;
        this.refreshing = false;
      },
    });
  }

  refresh(): void {
    this.refreshing = true;
    this.loadStatus();
  }

  trackByKeyPrefix(index: number, item: GeminiKeyStatusItem): string {
    return item.key_prefix;
  }

  maskKey(key: string): string {
    if (!key) return '—';
    const start = key.slice(0, 6);
    const end = key.slice(-4);
    return `${start}••••••••••${end}`;
  }

  hasCooldown(item: GeminiKeyStatusItem): boolean {
    return (item.cooldown_remaining_s || 0) > 0;
  }

  formatCooldown(item: GeminiKeyStatusItem): string {
    const remain = Math.max(0, Math.floor(item.cooldown_remaining_s || 0));
    if (remain <= 0) return '—';
    return `${remain}s`;
  }

  getCooldownBadgeClass(item: GeminiKeyStatusItem): string {
    if (this.hasCooldown(item)) return 'bg-red-100 text-red-700';
    return 'bg-green-100 text-green-700';
  }

  getErrorCount(item: GeminiKeyStatusItem, code: string): number {
    return item.error_counts?.[code] ?? 0;
  }

  // Build a sorted list of error entries across all statuses for display
  getErrorEntries(
    item: GeminiKeyStatusItem,
  ): Array<{ key: string; count: number }> {
    if (!item || !item.error_counts) return [];
    const entries = Object.entries(item.error_counts)
      .filter(([_, v]) => (v as number) > 0)
      .map(([k, v]) => ({ key: k, count: v as number }))
      // Sort descending by count, then by key
      .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
    return entries;
  }

  // Pretty label for some legacy aggregate keys
  formatErrorKey(key: string): string {
    if (key === 'auth_401_403') return '401/403';
    return key;
  }
}

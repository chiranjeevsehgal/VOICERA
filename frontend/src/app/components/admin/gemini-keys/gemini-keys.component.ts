import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { GeminiKeysService, GeminiKeysStatusResponse, GeminiKeyStatusItem } from '../../../services/admin/gemini-keys.service';

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

  constructor(private gemini: GeminiKeysService) {}

  ngOnInit(): void {
    this.loadStatus();
  }

  loadStatus(): void {
    if (!this.refreshing) {
      this.loading = true;
    }
    this.error = '';

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
}

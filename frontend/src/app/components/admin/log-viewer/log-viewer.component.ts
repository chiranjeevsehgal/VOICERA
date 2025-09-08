import { Component, OnDestroy, OnInit, ElementRef, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { LogsService, LogContentResponse } from '../../../services/admin/logs.service';

@Component({
  selector: 'app-log-viewer',
  standalone: true,
  imports: [CommonModule, HttpClientModule, FormsModule],
  providers: [LogsService],
  templateUrl: './log-viewer.component.html',
  styles: ``
})
export class LogViewerComponent implements OnInit, OnDestroy {
  loading = false;
  refreshing = false;
  error = '';
  
  filename = '';
  logContent: LogContentResponse | null = null;
  
  // Filters
  searchTerm = '';
  lineLimit = 1000;
  showFilters = false;
  
  // Display options
  wrapLines = true;
  showLineNumbers = true;
  fontSize = 'text-sm';
  showScrollToBottom = false;
  
  // Auto-refresh
  autoRefreshEnabled = false;
  private autoRefreshId?: number;
  private readonly autoRefreshMs = 3000;
  // Scroll behavior
  private firstLoad = true;
  
  // Incremental rendering
  logLines: string[] = [];
  private lastContentText: string = '';
  @ViewChild('logContainer') logContainer?: ElementRef<HTMLDivElement>;
  
  constructor(
    private route: ActivatedRoute,
    private router: Router,
    private logsService: LogsService
  ) {}

  ngOnInit(): void {
    this.route.params.subscribe(params => {
      this.filename = params['filename'];
      if (this.filename) {
        this.loadLogContent();
      }
    });
  }

  ngOnDestroy(): void {
    this.stopAutoRefresh();
  }

  loadLogContent(): void {
    this.loading = true;
    this.error = '';
    
    const lines = this.lineLimit > 0 ? this.lineLimit : undefined;
    const search = this.searchTerm.trim() || undefined;
    
    this.logsService.getLogFileContent(this.filename, lines, search).subscribe({
      next: (response: LogContentResponse) => {
        // Keep the raw response for download/copy
        this.logContent = response;
        // Update the incrementally rendered lines
        this.updateLinesFromContent(response.content || '');
        this.loading = false;
        this.refreshing = false;
      },
      error: (err) => {
        console.error('Failed to load log content', err);
        this.error = 'Failed to load log content. Please try again.';
        this.loading = false;
        this.refreshing = false;
      }
    });
  }

  refresh(): void {
    if (this.refreshing) return; // prevent overlapping
    this.refreshing = true;
    this.loadLogContent();
  }

  applyFilters(): void {
    this.loadLogContent();
  }

  clearFilters(): void {
    this.searchTerm = '';
    this.lineLimit = 1000;
    this.loadLogContent();
  }

  // Append-only update if server content grew with the previous content as a prefix.
  private updateLinesFromContent(content: string): void {
    const container = this.logContainer?.nativeElement;
    const wasAtBottom = this.isAtBottom(container);

    if (this.lastContentText && content.startsWith(this.lastContentText)) {
      const prevEndedWithNl = this.lastContentText.endsWith('\n');
      const newPart = content.substring(this.lastContentText.length);
      if (newPart.length > 0) {
        const newLinesRaw = newPart.split('\n');
        if (!prevEndedWithNl && this.logLines.length > 0) {
          // Merge first new fragment with the last existing line
          this.logLines[this.logLines.length - 1] += newLinesRaw.shift() ?? '';
        }
        // Append remaining complete lines
        if (newLinesRaw.length > 0) {
          this.logLines.push(...newLinesRaw);
        }
      }
    } else {
      // Fallback: replace entire buffer (first load or rotated/truncated log)
      this.logLines = content.split('\n');
    }

    this.lastContentText = content;

    // Always scroll to bottom on the first load
    if (this.firstLoad) {
      setTimeout(() => {
        this.scrollToBottom(this.logContainer?.nativeElement);
        this.showScrollToBottom = false;
      }, 0);
      this.firstLoad = false;
      return;
    }

    if (wasAtBottom) {
      // Scroll to bottom after DOM updates
      setTimeout(() => {
        this.scrollToBottom(this.logContainer?.nativeElement);
        this.showScrollToBottom = false;
      }, 0);
    } else {
      // Update the visibility of the button based on current position after render
      setTimeout(() => {
        this.showScrollToBottom = !this.isAtBottom(this.logContainer?.nativeElement);
      }, 0);
    }
  }

  private isAtBottom(el?: HTMLDivElement | null): boolean {
    if (!el) return true;
    const threshold = 40; // px tolerance
    return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
  }

  private scrollToBottom(el?: HTMLDivElement | null): void {
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }

  jumpToBottom(): void {
    this.scrollToBottom(this.logContainer?.nativeElement);
    this.showScrollToBottom = false;
  }

  onLogScroll(): void {
    const container = this.logContainer?.nativeElement;
    this.showScrollToBottom = !this.isAtBottom(container);
  }

  trackByIndex(index: number, _item: unknown): number {
    return index;
  }

  toggleFilters(): void {
    this.showFilters = !this.showFilters;
  }

  // Auto-refresh controls
  toggleAutoRefresh(): void {
    this.autoRefreshEnabled = !this.autoRefreshEnabled;
    if (this.autoRefreshEnabled) {
      // Do an immediate refresh, then schedule
      this.refresh();
      this.startAutoRefresh();
    } else {
      this.stopAutoRefresh();
    }
  }

  private startAutoRefresh(): void {
    this.stopAutoRefresh();
    this.autoRefreshId = window.setInterval(() => {
      // Avoid overlapping refreshes
      if (!this.refreshing) {
        this.refresh();
      }
    }, this.autoRefreshMs);
  }

  private stopAutoRefresh(): void {
    if (this.autoRefreshId) {
      window.clearInterval(this.autoRefreshId);
      this.autoRefreshId = undefined;
    }
  }

  goBack(): void {
    this.router.navigate(['/admin/dashboard']);
  }

  downloadLog(): void {
    if (!this.logContent) return;
    
    const blob = new Blob([this.logContent.content], { type: 'text/plain' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = this.filename;
    link.click();
    window.URL.revokeObjectURL(url);
  }

  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  formatDate(dateString: string): string {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) return '—';
    
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  }

  getLogLines(): string[] {
    if (!this.logContent?.content) return [];
    return this.logContent.content.split('\n');
  }

  highlightSearchTerm(line: string): string {
    if (!this.searchTerm.trim()) return line;
    
    const regex = new RegExp(`(${this.escapeRegExp(this.searchTerm)})`, 'gi');
    return line.replace(regex, '<mark class="bg-yellow-400 text-gray-900 px-1 rounded font-semibold">$1</mark>');
  }

  private escapeRegExp(string: string): string {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  getLineClass(line: string): string {
    const lowerLine = line.toLowerCase();
    
    if (lowerLine.includes('error') || lowerLine.includes('exception') || lowerLine.includes('failed')) {
      return 'text-red-400 bg-red-900/20 border-l-2 border-red-400';
    }
    if (lowerLine.includes('warning') || lowerLine.includes('warn')) {
      return 'text-yellow-300 bg-yellow-900/20 border-l-2 border-yellow-400';
    }
    if (lowerLine.includes('info') || lowerLine.includes('success')) {
      return 'text-blue-300 bg-blue-900/20 border-l-2 border-blue-400';
    }
    if (lowerLine.includes('debug')) {
      return 'text-gray-400';
    }
    
    return 'text-gray-200';
  }

  copyToClipboard(): void {
    if (!this.logContent?.content) return;
    
    navigator.clipboard.writeText(this.logContent.content).then(() => {
      // Could add a toast notification here
    }).catch(err => {
      console.error('Failed to copy to clipboard', err);
    });
  }
}

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpClientModule } from '@angular/common/http';
import { AnalyticsService, UsageAnalyticsResponse } from '../../../services/admin/analytics.service';

interface EndpointEntry { endpoint: string; path: string; method: string; count: number; }
interface IPEntry { ip: string; count: number; }

@Component({
  selector: 'app-usage-logs',
  standalone: true,
  imports: [CommonModule, HttpClientModule],
  providers: [AnalyticsService],
  templateUrl: './usage-logs.component.html',
  styles: ``,
})
export class UsageLogsComponent implements OnInit {
  loading = false;
  refreshing = false;
  error = '';

  totalRequests = 0;
  averageResponseTime = 0; // in ms
  endpointEntries: EndpointEntry[] = [];
  ipEntries: IPEntry[] = [];

  constructor(private analytics: AnalyticsService) {}

  ngOnInit(): void {
    this.loadAnalytics();
  }

  loadAnalytics(): void {
    this.loading = true;
    this.error = '';
    this.analytics.getUsageAnalytics().subscribe({
      next: (data: UsageAnalyticsResponse) => {
        this.totalRequests = data.total_requests || 0;
        this.averageResponseTime = data.average_response_time || 0;
        const counts = data.endpoint_counts || {};
        this.endpointEntries = Object.entries(counts)
          .map(([endpoint, count]) => {
            const { method, path } = this.parseEndpointKey(endpoint);
            return { endpoint, path, method, count } as EndpointEntry;
          })
          .sort((a, b) => b.count - a.count);

        const ipCounts = data.ip_counts || {};
        this.ipEntries = Object.entries(ipCounts)
          .map(([ip, count]) => ({ ip, count } as IPEntry))
          .sort((a, b) => b.count - a.count)
          .slice(0, 50);
        this.loading = false;
        this.refreshing = false;
      },
      error: (err) => {
        console.error('Failed to load usage analytics', err);
        this.error = 'Failed to load usage analytics. Please try again.';
        this.loading = false;
        this.refreshing = false;
      }
    });
  }

  refresh(): void {
    this.refreshing = true;
    this.loadAnalytics();
  }

  formatMs(ms: number): string {
    return `${Math.round(ms)} ms`;
  }

  trackByEndpoint(index: number, item: EndpointEntry): string {
    return item.endpoint;
  }

  trackByIp(index: number, item: IPEntry): string {
    return item.ip;
  }

  private parseEndpointKey(key: string): { method: string; path: string } {
    // Expect formats like: "GET /api/foo", "POST /api/bar" or just "/api/baz"
    const match = key.match(/^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(.+)$/i);
    if (match) {
      return { method: match[1].toUpperCase(), path: match[2] };
    }
    // If method not present, return UNKNOWN and original key as path
    return { method: 'UNKNOWN', path: key };
  }

  methodBadgeClass(method: string): string {
    switch (method) {
      case 'GET':
        return 'bg-green-100 text-green-800 ring-1 ring-inset ring-green-200';
      case 'POST':
        return 'bg-blue-100 text-blue-800 ring-1 ring-inset ring-blue-200';
      case 'PUT':
        return 'bg-amber-100 text-amber-800 ring-1 ring-inset ring-amber-200';
      case 'PATCH':
        return 'bg-purple-100 text-purple-800 ring-1 ring-inset ring-purple-200';
      case 'DELETE':
        return 'bg-red-100 text-red-800 ring-1 ring-inset ring-red-200';
      case 'OPTIONS':
      case 'HEAD':
        return 'bg-gray-100 text-gray-800 ring-1 ring-inset ring-gray-200';
      default:
        return 'bg-slate-100 text-slate-800 ring-1 ring-inset ring-slate-200';
    }
  }
}

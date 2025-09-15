import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
  AnalyticsService,
  UsageAnalyticsResponse,
  IPDetailedAnalytics,
  RealTimeAnalytics,
} from '../../../services/admin/analytics.service';
import { shouldUseMockData } from '../../../utils/role.utils';
import * as mockUsage from '../../../utils/mockData/mockUsageData.json';
import { HotToastService } from '@ngxpert/hot-toast';

interface EndpointEntry {
  endpoint: string;
  path: string;
  method: string;
  count: number;
  avgResponseTime?: number;
  successRate?: number;
}
interface IPEntry {
  ip: string;
  count: number;
  lastSeen?: string;
  avgResponseTime?: number;
  uniqueEndpoints?: number;
}

@Component({
  selector: 'app-usage-logs',
  standalone: true,
  imports: [CommonModule, FormsModule],
  providers: [AnalyticsService],
  templateUrl: './usage-logs.component.html',
  styles: ``,
})
export class UsageLogsComponent implements OnInit, OnDestroy {
  loading = false;
  refreshing = false;

  totalRequests = 0;
  averageResponseTime = 0; // in ms
  endpointEntries: EndpointEntry[] = [];
  ipEntries: IPEntry[] = [];

  // Filters and UI state
  showFilters = true;
  selectedDays: number = 7;
  filterIP: string = '';
  filterEndpoint: string = '';
  filterStatusCode: string = '';

  // Real-time
  realTimeMode = false;
  private pollHandle: any = null;

  // Additional analytics
  uniqueIPs = 0;
  errorRate = 0; // percentage
  statusCounts: Record<string, number> = {};

  // IP details modal
  selectedIPDetails: IPDetailedAnalytics | null = null;

  constructor(private analytics: AnalyticsService, private toast: HotToastService) {}

  ngOnInit(): void {
    this.loadAnalytics();
  }

  ngOnDestroy(): void {
    this.stopPolling();
  }

  loadAnalytics(): void {
    // Default load respects current filters
    this.applyFilters();
  }

  refresh(): void {
    this.refreshing = true;
    if (this.realTimeMode) {
      this.loadRealTime();
    } else {
      this.applyFilters();
    }
  }

  formatMs(ms?: number): string {
    if (ms === undefined || ms === null || isNaN(ms)) return '—';
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
    const match = key.match(
      /^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(.+)$/i,
    );
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

  // Filtering and helpers used by template
  toggleFilters(): void {
    this.showFilters = !this.showFilters;
  }

  clearFilters(): void {
    this.selectedDays = 7;
    this.filterIP = '';
    this.filterEndpoint = '';
    this.filterStatusCode = '';
    this.applyFilters();
  }

  applyFilters(): void {
    this.loading = true;
    const filters: any = {};
    if (this.selectedDays) filters.days = this.selectedDays;
    if (this.filterIP) filters.ip_address = this.filterIP.trim();
    if (this.filterEndpoint) filters.endpoint = this.filterEndpoint.trim();
    if (this.filterStatusCode)
      filters.status_code = Number(this.filterStatusCode);
    // Guest/Mock mode: build analytics locally from mock JSON
    if (shouldUseMockData()) {
      const data = mockUsage as any as UsageAnalyticsResponse;
      const endpointFilter = (this.filterEndpoint || '').toLowerCase();
      const ipFilter = (this.filterIP || '').toLowerCase();

      // Totals and summary
      this.totalRequests = data.total_requests || 0;
      this.averageResponseTime = data.average_response_time || 0;

      // Endpoints
      if (data.endpoint_details && data.endpoint_details.length > 0) {
        this.endpointEntries = data.endpoint_details
          .filter(
            (d) =>
              !endpointFilter ||
              d.endpoint.toLowerCase().includes(endpointFilter),
          )
          .map((d) => {
            const { method, path } = this.parseEndpointKey(d.endpoint);
            return {
              endpoint: d.endpoint,
              path,
              method,
              count: d.count,
              avgResponseTime: d.avg_response_time,
              successRate: d.success_rate,
            } as any;
          })
          .sort((a, b) => b.count - a.count);
      } else {
        const counts = data.endpoint_counts || {};
        this.endpointEntries = Object.entries(counts)
          .filter(
            ([endpoint]) =>
              !endpointFilter ||
              endpoint.toLowerCase().includes(endpointFilter),
          )
          .map(([endpoint, count]) => {
            const { method, path } = this.parseEndpointKey(endpoint);
            return {
              endpoint,
              path,
              method,
              count: count as number,
              avgResponseTime: undefined,
            } as any;
          })
          .sort((a, b) => b.count - a.count);
      }

      // IPs
      if ((data as any).ip_details && (data as any).ip_details.length > 0) {
        const ipDetails = (data as any).ip_details as Array<any>;
        this.ipEntries = ipDetails
          .filter(
            (ipd) =>
              !ipFilter || String(ipd.ip).toLowerCase().includes(ipFilter),
          )
          .map((ipd) => ({
            ip: ipd.ip,
            count: ipd.count,
            lastSeen: ipd.last_seen,
            avgResponseTime: ipd.avg_response_time,
            uniqueEndpoints: ipd.unique_endpoints,
          }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 50);
        this.uniqueIPs = ipDetails.length;
      } else {
        const ipCounts = data.ip_counts || {};
        this.ipEntries = Object.entries(ipCounts)
          .filter(([ip]) => !ipFilter || ip.toLowerCase().includes(ipFilter))
          .map(([ip, count]) => ({
            ip,
            count: count as number,
            lastSeen: undefined,
          }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 50);
        this.uniqueIPs = Object.keys(ipCounts).length;
      }

      // Status counts and error rate
      this.statusCounts = data.status_counts || {};
      const errorTotal = Object.entries(this.statusCounts)
        .filter(([code]) => {
          const c = Number(code);
          return !isNaN(c) && c >= 400;
        })
        .reduce((sum, [, cnt]) => sum + (cnt || 0), 0);
      this.errorRate =
        this.totalRequests > 0 ? (errorTotal / this.totalRequests) * 100 : 0;

      // Simulate network delay
      setTimeout(() => {
        this.loading = false;
        this.refreshing = false;
      }, 300);
      return;
    }

    this.analytics.getFilteredUsageAnalytics(filters).subscribe({
      next: (data: UsageAnalyticsResponse) => {
        this.totalRequests = data.total_requests || 0;
        this.averageResponseTime = data.average_response_time || 0;

        // Endpoints: prefer detailed metrics when available
        if (data.endpoint_details && data.endpoint_details.length > 0) {
          this.endpointEntries = data.endpoint_details
            .map((d) => {
              const { method, path } = this.parseEndpointKey(d.endpoint);
              return {
                endpoint: d.endpoint,
                path,
                method,
                count: d.count,
                avgResponseTime: d.avg_response_time,
                successRate: d.success_rate,
              } as EndpointEntry;
            })
            .sort((a, b) => b.count - a.count);
        } else {
          const counts = data.endpoint_counts || {};
          this.endpointEntries = Object.entries(counts)
            .map(([endpoint, count]) => {
              const { method, path } = this.parseEndpointKey(endpoint);
              return {
                endpoint,
                path,
                method,
                count,
                avgResponseTime: undefined,
              } as EndpointEntry;
            })
            .sort((a, b) => b.count - a.count);
        }

        // IPs: prefer detailed metrics when available
        if (data.ip_details && data.ip_details.length > 0) {
          this.ipEntries = data.ip_details
            .map(
              (ipd) =>
                ({
                  ip: ipd.ip,
                  count: ipd.count,
                  lastSeen: ipd.last_seen,
                  avgResponseTime: ipd.avg_response_time,
                  uniqueEndpoints: ipd.unique_endpoints,
                }) as IPEntry,
            )
            .sort((a, b) => b.count - a.count)
            .slice(0, 50);
        } else {
          const ipCounts = data.ip_counts || {};
          this.ipEntries = Object.entries(ipCounts)
            .map(
              ([ip, count]) => ({ ip, count, lastSeen: undefined }) as IPEntry,
            )
            .sort((a, b) => b.count - a.count)
            .slice(0, 50);
        }

        // Status counts and derived metrics
        this.statusCounts = data.status_counts || {};
        const errorTotal = Object.entries(this.statusCounts)
          .filter(([code]) => {
            const c = Number(code);
            return !isNaN(c) && c >= 400;
          })
          .reduce((sum, [, cnt]) => sum + (cnt || 0), 0);
        this.errorRate =
          this.totalRequests > 0 ? (errorTotal / this.totalRequests) * 100 : 0;

        // Unique IPs
        if (data.ip_details && data.ip_details.length > 0) {
          this.uniqueIPs = data.ip_details.length;
        } else {
          const ipCounts = data.ip_counts || {};
          this.uniqueIPs = Object.keys(ipCounts).length;
        }

        this.loading = false;
        this.refreshing = false;
      },
      error: (err) => {
        console.error('Failed to load usage analytics', err);
        this.toast.error('Failed to load usage analytics. Please try again.');
        this.loading = false;
        this.refreshing = false;
      },
    });
  }

  getStatusEntries(): Array<{ code: number; count: number }> {
    return Object.entries(this.statusCounts || {})
      .map(([code, count]) => ({ code: Number(code), count }))
      .filter((x) => !isNaN(x.code))
      .sort((a, b) => b.count - a.count);
  }

  getStatusColor(code: number): string {
    if (code >= 500) return 'text-red-600';
    if (code >= 400) return 'text-orange-600';
    if (code >= 300) return 'text-yellow-600';
    return 'text-green-600';
  }

  // IP details modal actions
  viewIPDetails(ip: string): void {
    // Mock IP details in Guest mode
    if (shouldUseMockData()) {
      const data = mockUsage as any;
      const ipd = (data.ip_details || []).find(
        (x: any) => String(x.ip) === String(ip),
      );
      if (!ipd) {
        this.selectedIPDetails = null;
        return;
      }
      const details: IPDetailedAnalytics = {
        ip_address: String(ipd.ip),
        summary: {
          total_requests: ipd.count || 0,
          unique_endpoints: ipd.unique_endpoints || 0,
          unique_user_agents: 0,
          unique_users: 0,
          avg_response_time: ipd.avg_response_time || 0,
          first_seen:
            ipd.first_seen ||
            (data.date_range?.start ?? new Date().toISOString()),
          last_seen:
            ipd.last_seen || (data.date_range?.end ?? new Date().toISOString()),
        },
        endpoints: (data.endpoint_details || []).slice(0, 10).map((e: any) => ({
          endpoint: e.endpoint,
          count: e.count,
          avg_response_time: e.avg_response_time || 0,
          last_accessed: data.date_range?.end ?? new Date().toISOString(),
          success_rate: e.success_rate ?? 1.0,
        })),
        hourly_pattern: data.hourly_distribution || {},
        daily_activity: [],
        status_distribution: data.status_counts || {},
        user_agents: [],
        date_range: data.date_range || {
          start: new Date().toISOString(),
          end: new Date().toISOString(),
        },
      };
      // Simulate delay
      setTimeout(() => {
        this.selectedIPDetails = details;
      }, 200);
      return;
    }

    this.analytics
      .getIPDetailedAnalytics(ip, this.selectedDays || 30)
      .subscribe({
        next: (details: IPDetailedAnalytics) => {
          this.selectedIPDetails = details;
        },
        error: (err) => {
          console.error('Failed to load IP details', err);
          this.toast.error('Failed to load IP details. Please try again.');
        },
      });
  }

  closeIPDetails(): void {
    this.selectedIPDetails = null;
  }

  filterByIP(ip: string): void {
    this.filterIP = ip;
    this.applyFilters();
  }

  formatDate(iso?: string): string {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleString();
  }

  // Real-time mode
  toggleRealTime(): void {
    if (this.realTimeMode) {
      this.startPolling();
      this.loadRealTime();
    } else {
      this.stopPolling();
      this.applyFilters();
    }
  }

  private startPolling(): void {
    this.stopPolling();
    this.pollHandle = setInterval(() => this.loadRealTime(), 30_000);
  }

  private stopPolling(): void {
    if (this.pollHandle) {
      clearInterval(this.pollHandle);
      this.pollHandle = null;
    }
  }

  private loadRealTime(): void {
    this.loading = this.endpointEntries.length === 0; // show overlay on first load
    // Mock real-time analytics for Guest mode
    if (shouldUseMockData()) {
      const data = mockUsage as any as UsageAnalyticsResponse;
      // Summary
      this.totalRequests = data.total_requests || 0;
      this.averageResponseTime = data.average_response_time || 0;
      this.uniqueIPs = (data as any).ip_details
        ? (data as any).ip_details.length
        : Object.keys(data.ip_counts || {}).length;
      const status = data.status_counts || {};
      const errorTotal = Object.entries(status)
        .filter(([code]) => {
          const c = Number(code);
          return !isNaN(c) && c >= 400;
        })
        .reduce((sum, [, cnt]) => sum + (cnt || 0), 0);
      this.errorRate =
        this.totalRequests > 0 ? (errorTotal / this.totalRequests) * 100 : 0;

      // Endpoints (top)
      const details = data.endpoint_details || [];
      this.endpointEntries = (
        details.length > 0
          ? details
          : Object.entries(data.endpoint_counts || {}).map(
              ([endpoint, count]) =>
                ({
                  endpoint,
                  count: count as number,
                  avg_response_time: undefined,
                }) as any,
            )
      )
        .map((d: any) => {
          const endpoint = d.endpoint || d.endpoint;
          const { method, path } = this.parseEndpointKey(endpoint);
          return {
            endpoint,
            path,
            method,
            count: d.count ?? d.requests ?? d.count,
            avgResponseTime: d.avg_response_time,
          } as any;
        })
        .sort((a, b) => b.count - a.count)
        .slice(0, 20);

      // IPs
      if ((data as any).ip_details && (data as any).ip_details.length > 0) {
        this.ipEntries = ((data as any).ip_details as any[])
          .map((ip: any) => ({
            ip: ip.ip,
            count: ip.count,
            lastSeen: ip.last_seen,
            avgResponseTime: ip.avg_response_time,
            uniqueEndpoints: ip.unique_endpoints,
          }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 50);
      } else {
        const ipCounts = data.ip_counts || {};
        this.ipEntries = Object.entries(ipCounts)
          .map(([ip, count]) => ({
            ip,
            count: count as number,
            lastSeen: undefined,
          }))
          .sort((a, b) => b.count - a.count)
          .slice(0, 50);
      }

      this.loading = false;
      this.refreshing = false;
      return;
    }

    this.analytics.getRealTimeAnalytics(60).subscribe({
      next: (rt: RealTimeAnalytics) => {
        // Summary
        this.totalRequests = rt.summary.total_requests || 0;
        this.averageResponseTime = rt.summary.avg_response_time || 0;
        this.uniqueIPs = rt.summary.unique_ips || 0;
        this.errorRate = rt.summary.error_rate || 0;

        // Endpoints
        this.endpointEntries = (rt.top_endpoints || [])
          .map((te) => {
            const { method, path } = this.parseEndpointKey(te.endpoint);
            return {
              endpoint: te.endpoint,
              path,
              method,
              count: te.requests,
              avgResponseTime: te.avg_response_time,
            } as EndpointEntry;
          })
          .sort((a, b) => b.count - a.count);

        // IPs
        this.ipEntries = (rt.active_ips || [])
          .map(
            (ip) =>
              ({
                ip: ip.ip,
                count: ip.requests,
                lastSeen: ip.last_seen,
              }) as IPEntry,
          )
          .sort((a, b) => b.count - a.count)
          .slice(0, 50);

        // No explicit status distribution in real-time response; leave previous or clear
        // this.statusCounts = {};

        this.loading = false;
        this.refreshing = false;
      },
      error: (err) => {
        console.error('Failed to load real-time analytics', err);
        this.toast.error('Failed to load real-time analytics. Please try again.');
        this.loading = false;
        this.refreshing = false;
      },
    });
  }
}

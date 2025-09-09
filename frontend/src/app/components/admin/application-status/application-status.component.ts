import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import {
  SystemHealthService,
  SystemHealthResponse,
  CircuitBreakersResponse,
  RateLimitsResponse,
  CircuitBreakerState,
} from '../../../services/admin/system-health.service';
import {
  LucideAngularModule,
  Activity,
  Shield,
  Zap,
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Clock,
  Settings,
} from 'lucide-angular';

import { shouldUseMockData } from '../../../utils/role.utils';
import * as mockHealthData from '../../../utils/mockData/mockHealth.json';
import * as mockCircuitBreakersData from '../../../utils/mockData/mockCircuitBreakers.json';
import * as mockRateLimitsData from '../../../utils/mockData/mockRateLimits.json';
import { HotToastService } from '@ngxpert/hot-toast';

@Component({
  selector: 'app-application-status',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    HttpClientModule,
    LucideAngularModule,
  ],
  providers: [SystemHealthService],
  templateUrl: './application-status.component.html',
  styles: ``,
})
export class ApplicationStatusComponent implements OnInit {
  // Icons
  readonly Activity = Activity;
  readonly Shield = Shield;
  readonly Zap = Zap;
  readonly RefreshCw = RefreshCw;
  readonly AlertTriangle = AlertTriangle;
  readonly CheckCircle = CheckCircle;
  readonly Clock = Clock;
  readonly Settings = Settings;

  // Data properties
  systemHealth: SystemHealthResponse | null = null;
  circuitBreakers: CircuitBreakersResponse | null = null;
  rateLimits: RateLimitsResponse | null = null;

  // UI state properties
  loading: boolean = false;
  refreshing: boolean = false;
  resettingCircuitBreakers: boolean = false;
  lastRefresh: Date | null = null;

  // Auto refresh
  private refreshInterval: any;
  autoRefreshEnabled: boolean = true;
  refreshIntervalSeconds: number = 30;

  constructor(
    private systemHealthService: SystemHealthService,
    private toast: HotToastService,
  ) {}

  ngOnInit() {
    this.loadAllData();
    this.startAutoRefresh();
  }

  ngOnDestroy() {
    this.stopAutoRefresh();
  }

  async loadAllData() {
    this.loading = true;
    // Use mock data for Guests
    if (shouldUseMockData()) {
      const health = mockHealthData as SystemHealthResponse;
      const circuits = mockCircuitBreakersData as CircuitBreakersResponse;
      const rateLimits = mockRateLimitsData as RateLimitsResponse;
      await new Promise((resolve) => setTimeout(resolve, 500));
      this.systemHealth = health;
      this.circuitBreakers = circuits;
      this.rateLimits = rateLimits;
      this.lastRefresh = new Date();
      this.loading = false;
      this.refreshing = false;
      return;
    }

    try {
      // Load all data in parallel
      const [healthData, circuitData, rateLimitData] = await Promise.all([
        this.systemHealthService.getSystemHealth().toPromise(),
        this.systemHealthService.getCircuitBreakers().toPromise(),
        this.systemHealthService.getRateLimits().toPromise(),
      ]);

      this.systemHealth = healthData!;
      this.circuitBreakers = circuitData!;
      this.rateLimits = rateLimitData!;
      this.lastRefresh = new Date();
    } catch (error: any) {
      this.toast.error("Failed to load system status");
    } finally {
      this.loading = false;
      this.refreshing = false;
    }
  }

  async refreshData() {
    this.refreshing = true;
    await this.loadAllData();
  }

  async resetCircuitBreakers() {
    if (
      !confirm(
        'Are you sure you want to reset all circuit breakers? This will restore all services to normal operation.',
      )
    ) {
      return;
    }

    this.resettingCircuitBreakers = true;
    // Simulate reset in Guest/Mock mode
    if (shouldUseMockData()) {
      await new Promise((resolve) => setTimeout(resolve, 400));
      // Refresh data after reset
      await this.loadAllData();
      this.resettingCircuitBreakers = false;
      return;
    }

    try {
      const result = await this.systemHealthService
        .resetCircuitBreakers()
        .toPromise();

      this.toast.success('Circuit breakers reset successfully');

      // Refresh data after reset
      await this.loadAllData();
    } catch (error: any) {
      
      this.toast.error('Failed to reset circuit breakers');
    } finally {
      this.resettingCircuitBreakers = false;
    }
  }

  startAutoRefresh() {
    if (this.autoRefreshEnabled) {
      this.refreshInterval = setInterval(() => {
        if (!this.loading && !this.refreshing) {
          this.refreshData();
        }
      }, this.refreshIntervalSeconds * 1000);
    }
  }

  stopAutoRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }

  toggleAutoRefresh() {
    this.autoRefreshEnabled = !this.autoRefreshEnabled;
    if (this.autoRefreshEnabled) {
      this.startAutoRefresh();
    } else {
      this.stopAutoRefresh();
    }
  }

  getCircuitBreakerStateColor(state: string): string {
    switch (state) {
      case 'closed':
        return 'text-green-600 bg-green-50';
      case 'open':
        return 'text-red-600 bg-red-50';
      case 'half_open':
        return 'text-yellow-600 bg-yellow-50';
      default:
        return 'text-gray-600 bg-gray-50';
    }
  }

  getCircuitBreakerStateIcon(state: string) {
    switch (state) {
      case 'closed':
        return CheckCircle;
      case 'open':
        return AlertTriangle;
      case 'half_open':
        return Clock;
      default:
        return Settings;
    }
  }

  getSystemHealthStatus(): { color: string; icon: any; text: string } {
    if (!this.systemHealth) {
      return { color: 'text-gray-600', icon: Settings, text: 'Unknown' };
    }

    const openCircuits = this.circuitBreakers?.summary?.open || 0;

    if (openCircuits > 0) {
      return { color: 'text-red-600', icon: AlertTriangle, text: 'Degraded' };
    }

    if (this.systemHealth.status === 'healthy') {
      return { color: 'text-green-600', icon: CheckCircle, text: 'Healthy' };
    }

    return { color: 'text-yellow-600', icon: Clock, text: 'Warning' };
  }

  formatBytes(bytes: number | string): string {
    if (typeof bytes === 'string') return bytes;
    if (bytes === 0) return '0 B';

    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));

    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  formatDuration(seconds: number): string {
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  }

  getObjectKeys(obj: any): string[] {
    return Object.keys(obj || {});
  }

  formatTimestamp(timestamp: number): string {
    if (!timestamp) return 'Never';
    return new Date(timestamp * 1000).toLocaleString();
  }

  trackByFn(index: number, item: string): string {
    return item;
  }
}

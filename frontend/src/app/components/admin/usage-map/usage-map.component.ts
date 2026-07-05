import { Component, ElementRef, OnDestroy, OnInit, ViewChild, AfterViewInit } from '@angular/core';

import { AnalyticsService } from '../../../services/admin/analytics.service';
import { firstValueFrom } from 'rxjs';

@Component({
  selector: 'app-usage-map',
  standalone: true,
  imports: [],
  templateUrl: './usage-map.component.html',
  styles: [
    `
    :host { display: block; }
    .map-container { width: 100%; height: 520px; }
    .hint { color: #64748b; font-size: 12px; }
    `,
  ],
})
export class UsageMapComponent implements OnInit, AfterViewInit, OnDestroy {
  @ViewChild('chart', { static: false }) chartRef!: ElementRef<HTMLDivElement>;
  private chart: any | null = null;
  loading = true;
  error: string | null = null;
  data: Array<{ country_code: string; country: string | null; count: number }> = [];
  private centroids: Record<string, [number, number]> = {};
  private readonly savedGeoKey = 'usageMapGeo';
  private nameIndex: Record<string, string> = {};

  constructor(private analytics: AnalyticsService) {}

  async ngOnInit(): Promise<void> {}

  async ngAfterViewInit(): Promise<void> {
    // Use setTimeout to ensure DOM is fully rendered
    setTimeout(async () => {
      try {
        await this.ensureEchartsLoaded();
        await this.loadData();
        this.initChart();
        window.addEventListener('resize', this.handleResize);
      } catch (e: any) {
        console.error('UsageMap init failed:', e);
        this.error = 'Failed to load usage map';
      } finally {
        this.loading = false;
      }
    }, 100);
  }

  ngOnDestroy(): void {
    window.removeEventListener('resize', this.handleResize);
    if (this.chart && (window as any).echarts) {
      try { this.chart.dispose(); } catch {}
    }
  }

  private handleResize = () => {
    if (this.chart) {
      try { this.chart.resize(); } catch {}
    }
  };

  private async loadData(): Promise<void> {
    const resp = await firstValueFrom(this.analytics.getIpGeoSummary());
    this.data = resp?.items || [];
  }

  private async ensureEchartsLoaded(): Promise<void> {
    const w = window as any;
    if (w.echarts && w.echarts.registerMap) {
      // world map script might already be present; ensure it's loaded
      if (!w._worldMapLoaded) {
        await this.loadScript('https://cdn.jsdelivr.net/npm/echarts-maps@1.1.0/world.min.js');
        w._worldMapLoaded = true;
      }
      return;
    }
    await this.loadScript('https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js');
    await this.loadScript('https://cdn.jsdelivr.net/npm/echarts-maps@1.1.0/world.min.js');
    w._worldMapLoaded = true;
  }

  private loadScript(src: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${src}"]`) as HTMLScriptElement | null;
      if (existing) {
        if (existing.getAttribute('data-loaded') === 'true') return resolve();
        existing.addEventListener('load', () => resolve());
        existing.addEventListener('error', () => reject(new Error(`Failed to load ${src}`)));
        return;
      }
      const s = document.createElement('script');
      s.src = src;
      s.async = true;
      s.onload = () => { s.setAttribute('data-loaded', 'true'); resolve(); };
      s.onerror = () => reject(new Error(`Failed to load ${src}`));
      document.body.appendChild(s);
    });
  }

  private initChart(): void {
    const w = window as any;
    if (!w.echarts) {
      this.error = 'Visualization library unavailable';
      return;
    }
    if (!this.chartRef || !this.chartRef.nativeElement) {
      console.error('UsageMap: chart container not found at init time');
      this.error = 'Failed to load usage map';
      return;
    }
    // Dispose previous instance if any (safety against double-init)
    if (this.chart && w.echarts) {
      try { this.chart.dispose(); } catch {}
      this.chart = null;
    }
    this.chart = w.echarts.init(this.chartRef.nativeElement);

    // Build centroid map and name index from echarts world geojson
    this.centroids = {};
    this.nameIndex = {};
    try {
      const world = w.echarts.getMap('world');
      const features: any[] = world && (world.geoJson?.features || world.geoJSON?.features) || [];
      const centroidOf = (coords: any): [number, number] => {
        // coords is an array of [ [ [lon, lat], ... ] ] for Polygon/MultiPolygon
        let sumX = 0, sumY = 0, n = 0;
        const walk = (arr: any) => {
          if (!Array.isArray(arr)) return;
          if (typeof arr[0] === 'number' && typeof arr[1] === 'number') {
            sumX += arr[0]; sumY += arr[1]; n += 1; return;
          }
          for (const sub of arr) walk(sub);
        };
        walk(coords);
        if (n === 0) return [0, 0];
        return [sumX / n, sumY / n];
      };
      for (const f of features) {
        const name: string = f.properties?.name || '';
        const coords = f.geometry?.coordinates;
        if (name && coords) {
          const c = centroidOf(coords);
          this.centroids[name] = c;
          const key = this.normalizeCountryKey(name);
          if (key) this.nameIndex[key] = name;
        }
      }
    } catch {}

    // Aggregate data by resolved country name to avoid overlapping bubbles per state
    const aggregate = new Map<string, number>();
    for (const d of (this.data || [])) {
      const resolved = this.resolveCountryName(d.country, d.country_code);
      if (!resolved) continue;
      aggregate.set(resolved, (aggregate.get(resolved) || 0) + (d.count || 0));
    }
    const areaData = Array.from(aggregate.entries()).map(([name, value]) => ({ name, value }));
    const max = areaData.reduce((m, x) => Math.max(m, x.value), 0) || 1;
    const option = {
      backgroundColor: '#ffffff',
      aria: { enabled: true },
      tooltip: {
        trigger: 'item',
        formatter: (params: any) => {
          return `${params.name}: ${params.value || 0}`;
        },
      },
      toolbox: {
        right: 10,
        top: 10,
        feature: {
          restore: { title: 'Reset' },
          saveAsImage: { title: 'Save' },
        },
      },
      animationDuration: 600,
      animationDurationUpdate: 300,
      visualMap: {
        min: 0,
        max,
        calculable: true,
        orient: 'horizontal',
        left: 'center',
        bottom: 10,
        inRange: {
          color: ['#e0f2fe', '#3b82f6'],
        },
      },
      geo: {
        map: 'world',
        zoom: 0.6,
        roam: true,
        silent: false,
        scaleLimit: { min: 1, max: 20 },
        itemStyle: {
          areaColor: 'transparent',
          borderColor: '#94a3b8',
        },
        emphasis: { itemStyle: { areaColor: '#c7d2fe' } },
        zlevel: 0,
      },
      series: [
        {
          name: 'Usage by Country',
          type: 'map',
          geoIndex: 0,
          selectedMode: 'single',
          emphasis: { label: { show: true }, itemStyle: { areaColor: '#c7d2fe' } },
          data: areaData,
          // Keep area layer subtle beneath bubbles
          itemStyle: { areaColor: '#eef2ff' },
          zlevel: 0,
        },
      ],
    } as any;

    // Restore last view (zoom/center) if available
    try {
      const saved = localStorage.getItem(this.savedGeoKey);
      if (saved) {
        const s = JSON.parse(saved);
        if (s.zoom) (option as any).geo.zoom = s.zoom;
        if (s.center) (option as any).geo.center = s.center;
      }
    } catch {}

    this.chart.setOption(option);

    // Persist view state on zoom/pan
    this.chart.on('georoam', () => {
      try {
        const opt = this.chart!.getOption();
        const g = (opt.geo && opt.geo[0]) || {};
        const state = { zoom: g.zoom || 1, center: g.center || null } as any;
        localStorage.setItem(this.savedGeoKey, JSON.stringify(state));
      } catch {}
    });

    // Click to focus on a country (or bubble) - ignore raw geo clicks to avoid duplicate triggers
    this.chart.on('click', (params: any) => {
      if (params?.componentType === 'geo') return;
      let name = params?.name as string;
      if (!name) return;
      const c = this.centroids[name];
      if (c) this.focusOn(c);
    });
  }

  private focusOn(coord: [number, number], zoom = 3): void {
    if (!this.chart) return;
    this.chart.setOption({ geo: { center: coord, zoom } });
  }

  private adjustZoom(factor: number): void {
    if (!this.chart) return;
    const opt = this.chart.getOption();
    const g = (opt.geo && opt.geo[0]) || {};
    const newZoom = Math.min(20, Math.max(1, (g.zoom || 1) * factor));
    this.chart.setOption({ geo: { zoom: newZoom } });
  }

  zoomIn(): void { this.adjustZoom(1.25); }
  zoomOut(): void { this.adjustZoom(0.8); }
  resetView(): void {
    if (!this.chart) return;
    this.chart.dispatchAction({ type: 'restore' });
    try { localStorage.removeItem(this.savedGeoKey); } catch {}
  }

  private normalizeCountryKey(s: string | null | undefined): string {
    if (!s) return '';
    return s
      .toLowerCase()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '') // strip diacritics
      .replace(/[^a-z0-9]+/g, ' ')
      .trim()
      .replace(/\s+/g, ' ');
  }

  private resolveCountryName(country: string | null, code?: string | null): string | null {
    // 1) Try by provided country name
    const byNameKey = this.normalizeCountryKey(country || '');
    if (byNameKey && this.nameIndex[byNameKey]) return this.nameIndex[byNameKey];
    // 1b) Try common alias names -> map to ECharts canonical name
    const aliasMap: Record<string, string> = {
      'united states': 'United States of America',
      'u s a': 'United States of America',
      'usa': 'United States of America',
      'russian federation': 'Russia',
      'south korea': 'Korea',
      'north korea': 'Dem. Rep. Korea',
      'czechia': 'Czech Rep.',
      'ivory coast': "Cote d'Ivoire",
      'democratic republic of the congo': 'Dem. Rep. Congo',
      'republic of the congo': 'Congo',
      'laos': 'Lao PDR',
      'north macedonia': 'Macedonia',
    };
    if (byNameKey && aliasMap[byNameKey]) {
      const key = this.normalizeCountryKey(aliasMap[byNameKey]);
      if (this.nameIndex[key]) return this.nameIndex[key];
    }
    // 2) Try common ISO alpha-2 mappings
    const c2 = (code || '').toUpperCase();
    const isoMap: Record<string, string> = {
      US: 'United States of America',
      GB: 'United Kingdom',
      RU: 'Russia',
      IR: 'Iran',
      VN: 'Vietnam',
      KR: 'Korea',
      KP: 'Dem. Rep. Korea',
      CZ: 'Czech Rep.',
      CD: 'Dem. Rep. Congo',
      CG: 'Congo',
      TZ: 'Tanzania',
      SY: 'Syria',
      BO: 'Bolivia',
      VE: 'Venezuela',
      LA: 'Lao PDR',
      CI: "Cote d'Ivoire",
      PS: 'Palestine',
      AE: 'United Arab Emirates',
      TW: 'Taiwan',
      XK: 'Kosovo',
      MD: 'Moldova',
      MK: 'Macedonia',
      SZ: 'Eswatini',
      MM: 'Myanmar',
      LY: 'Libya',
      KZ: 'Kazakhstan',
      AM: 'Armenia',
      AZ: 'Azerbaijan',
      GE: 'Georgia',
      BA: 'Bosnia and Herz.',
      DO: 'Dominican Rep.',
      SD: 'Sudan',
      SS: 'South Sudan',
      EH: 'W. Sahara',
      TG: 'Togo',
      CGO: 'Congo',
      SL: 'Sierra Leone',
      YE: 'Yemen',
      // Common straightforward ones map to their canonical names
      IN: 'India', CN: 'China', JP: 'Japan', DE: 'Germany', FR: 'France', ES: 'Spain', IT: 'Italy',
      BR: 'Brazil', CA: 'Canada', MX: 'Mexico', AU: 'Australia', NZ: 'New Zealand',
      SA: 'Saudi Arabia', TR: 'Turkey', EG: 'Egypt', ZA: 'South Africa', NG: 'Nigeria',
      PK: 'Pakistan', BD: 'Bangladesh', ID: 'Indonesia', TH: 'Thailand', PH: 'Philippines', MY: 'Malaysia', SG: 'Singapore',
      SE: 'Sweden', NO: 'Norway', FI: 'Finland', DK: 'Denmark', NL: 'Netherlands', BE: 'Belgium', CH: 'Switzerland', AT: 'Austria',
      PL: 'Poland', PT: 'Portugal', GR: 'Greece', IE: 'Ireland', HU: 'Hungary', RO: 'Romania', UA: 'Ukraine', BY: 'Belarus',
      MA: 'Morocco', DZ: 'Algeria', TN: 'Tunisia', KE: 'Kenya', ET: 'Ethiopia', GH: 'Ghana',
      AR: 'Argentina', CL: 'Chile', CO: 'Colombia', PE: 'Peru'
    };
    const mapped = isoMap[c2];
    if (mapped) {
      const key = this.normalizeCountryKey(mapped);
      if (this.nameIndex[key]) return this.nameIndex[key];
    }
    return null;
  }
}

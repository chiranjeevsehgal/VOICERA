import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { VectorVisualizationService } from '../../../services/admin/vector-visualization.service';

interface VectorPoint {
  id?: string;
  x: number;
  y: number;
  z: number;
  file_name?: string;
  chunk_index?: number;
  total_chunks?: number;
  start_time?: number;
  end_time?: number;
  text?: string;
}

@Component({
  selector: 'app-vector-visualization',
  standalone: true,
  imports: [CommonModule, FormsModule],
  providers: [VectorVisualizationService],
  templateUrl: './vector-visualization.component.html',
})
export class VectorVisualizationComponent implements OnInit {
  loading = false;
  error: string | null = null;
  total = 0;

  // UI options
  topK = 1000;
  fileNameContains = '';
  markerSize = 4;
  markerOpacity = 0.85;
  viewMode: '3d' | '2d' = '3d';
  hoverLength = 200;
  groupBy: 'file_name' | 'none' = 'file_name';

  constructor(private vecService: VectorVisualizationService) {}

  ngOnInit(): void {
    this.fetchAndRender();
  }

  private fetchAndRender(): void {
    this.loading = true;
    this.error = null;
    this.vecService
      .getVectorSpace(this.topK, {
        fileNameContains: this.fileNameContains?.trim() || undefined,
      })
      .subscribe({
        next: (res: { points: VectorPoint[] }) => {
          const points: VectorPoint[] = res?.points || [];
          this.total = points.length;
          this.renderPlot(points);
          this.loading = false;
        },
        error: (err: unknown) => {
          console.error('Failed to load vector space', err);
          this.error = 'Failed to load vector space. Please try again.';
          this.loading = false;
        },
      });
  }

  applyOptions(): void {
    this.fetchAndRender();
  }

  resetOptions(): void {
    this.topK = 1000;
    this.fileNameContains = '';
    this.markerSize = 4;
    this.markerOpacity = 0.85;
    this.viewMode = '3d';
    this.hoverLength = 200;
    this.groupBy = 'file_name';
    this.fetchAndRender();
  }

  resetCamera(): void {
    const Plotly = (window as any).Plotly;
    const container = document.getElementById('vector-3d-plot');
    if (!Plotly || !container) return;
    if (this.viewMode === '3d') {
      Plotly.relayout(container, {
        'scene.camera': {
          eye: { x: 1.25, y: 1.25, z: 1.25 },
          up: { x: 0, y: 0, z: 1 },
          center: { x: 0, y: 0, z: 0 },
        },
      });
    } else {
      Plotly.relayout(container, { 'xaxis.autorange': true, 'yaxis.autorange': true });
    }
  }

  async downloadImage(): Promise<void> {
    const Plotly = (window as any).Plotly;
    const container = document.getElementById('vector-3d-plot');
    if (!Plotly || !container) return;
    try {
      const dataUrl = await Plotly.toImage(container, { format: 'png', height: 800, width: 1200 });
      const a = document.createElement('a');
      a.href = dataUrl;
      a.download = 'vector-space.png';
      a.click();
    } catch (e) {
      console.error('Failed to export image', e);
    }
  }

  private renderPlot(points: VectorPoint[]): void {
    const Plotly = (window as any).Plotly;
    const container = document.getElementById('vector-3d-plot');

    if (!Plotly || !container) {
      this.error = 'Plotly not loaded.';
      return;
    }

    if (!points || points.length === 0) {
      Plotly.purge(container);
      return;
    }

    // Build hover texts
    const hoverTexts = points.map((p) => {
      const text = (p.text || '').slice(0, Math.max(0, this.hoverLength));
      return `File: ${p.file_name || 'unknown'}<br>` +
        `Chunk: ${p.chunk_index ?? 'NA'} / ${p.total_chunks ?? 'NA'}<br>` +
        `Time: ${(p.start_time ?? 0).toFixed(2)}–${(p.end_time ?? 0).toFixed(2)}s<br>` +
        `Text: ${text}...`;
    });

    // Create traces
    const palette = [
      '#636EFA', '#EF553B', '#00CC96', '#AB63FA', '#FFA15A',
      '#19D3F3', '#FF6692', '#B6E880', '#FF97FF', '#FECB52',
      '#2CA02C', '#9467BD', '#8C564B', '#E377C2', '#7F7F7F',
    ];

    let traces: any[] = [];
    if (this.groupBy === 'file_name') {
      const groups = new Map<string, VectorPoint[]>();
      points.forEach((p) => {
        const key = p.file_name || 'unknown';
        const arr = groups.get(key) || [];
        arr.push(p);
        groups.set(key, arr);
      });

      let idx = 0;
      for (const [file, pts] of groups.entries()) {
        const color = palette[idx % palette.length];
        const groupHover = pts.map((_, i) => hoverTexts[points.indexOf(pts[i])]);
        if (this.viewMode === '3d') {
          traces.push({
            name: file,
            x: pts.map((p) => p.x),
            y: pts.map((p) => p.y),
            z: pts.map((p) => p.z),
            mode: 'markers',
            type: 'scatter3d',
            text: groupHover,
            hoverinfo: 'text',
            marker: { size: this.markerSize, color, opacity: this.markerOpacity },
          });
        } else {
          traces.push({
            name: file,
            x: pts.map((p) => p.x),
            y: pts.map((p) => p.y),
            mode: 'markers',
            type: 'scatter',
            text: groupHover,
            hoverinfo: 'text',
            marker: { size: this.markerSize, color, opacity: this.markerOpacity },
          });
        }
        idx++;
      }
    } else {
      // Single-trace mode without grouping
      if (this.viewMode === '3d') {
        traces = [{
          x: points.map((p) => p.x),
          y: points.map((p) => p.y),
          z: points.map((p) => p.z),
          mode: 'markers',
          type: 'scatter3d',
          text: hoverTexts,
          hoverinfo: 'text',
          marker: { size: this.markerSize, color: '#636EFA', opacity: this.markerOpacity },
        }];
      } else {
        traces = [{
          x: points.map((p) => p.x),
          y: points.map((p) => p.y),
          mode: 'markers',
          type: 'scatter',
          text: hoverTexts,
          hoverinfo: 'text',
          marker: { size: this.markerSize, color: '#636EFA', opacity: this.markerOpacity },
        }];
      }
    }

    const layout: any = {
      title: `Vector Space (PCA ${this.viewMode.toUpperCase()}) — ${points.length} points`,
      autosize: true,
      height: 600,
      margin: { l: 0, r: 0, b: 0, t: 50 },
      showlegend: this.groupBy === 'file_name',
    };

    if (this.viewMode === '3d') {
      layout.scene = {
        xaxis: { title: 'PC1' },
        yaxis: { title: 'PC2' },
        zaxis: { title: 'PC3' },
      };
    } else {
      layout.xaxis = { title: 'PC1' };
      layout.yaxis = { title: 'PC2' };
    }

    Plotly.newPlot(container, traces, layout, { responsive: true });
  }
}

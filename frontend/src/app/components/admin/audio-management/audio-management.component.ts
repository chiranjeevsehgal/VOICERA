import { Component, OnDestroy, OnInit, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import {
  AudioService,
  Podcast,
  AudioRelationsResponse,
  RelationsEdge,
  RelationsNode,
} from '../../../services/admin/audio-management.service';
import { HotToastService } from '@ngxpert/hot-toast';
import { Subject } from 'rxjs';
import { debounceTime, distinctUntilChanged } from 'rxjs/operators';

@Component({
  selector: 'app-audio-management',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule],
  providers: [AudioService],
  templateUrl: './audio-management.component.html',
  styles: ``,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class AudioManagementComponent implements OnInit, OnDestroy {
  podcasts: Podcast[] = [];
  filteredPodcasts: Podcast[] = [];
  searchQuery: string = '';
  selectedAuthor: string = '';
  loading: boolean = false;
  refreshing: boolean = false;
  error: string = '';
  showDeleteModal: boolean = false;
  podcastToDelete: Podcast | null = null;
  deleting: boolean = false;
  showEditModal: boolean = false;
  podcastToEdit: Podcast | null = null;
  updating: boolean = false;
  editForm = {
    title: '',
  };

  // Relations modal state
  showRelationsModal: boolean = false;
  relationsLoading: boolean = false;
  relationsError: string = '';
  relationsData: AudioRelationsResponse | null = null;
  svgWidth: number = 1000;
  svgHeight: number = 600;
  positionedNodes: Array<{ id: string; label: string; type: string; x: number; y: number; color: string; r: number }> = [];
  graphEdges: RelationsEdge[] = [];
  edgesDraw: Array<{ from: string; to: string; x1: number; y1: number; x2: number; y2: number }> = [];
  groupRects: Array<{ id: string; label: string; x: number; y: number; width: number; height: number; color: string }> = [];

  // Interactions: pan/zoom
  zoomScale: number = 1;
  panX: number = 0;
  panY: number = 0;
  isPanning: boolean = false;
  lastMouseX: number = 0;
  lastMouseY: number = 0;
  graphTransform: string = 'translate(0,0) scale(1)';

  // Collapsible groups
  showMongo: boolean = true;
  showSupabase: boolean = true;
  showPinecone: boolean = true;

  // Collapsible JSON blocks in details panel
  showTranscriptQueries: boolean = false;
  showUploadQueries: boolean = false;

  // Tooltip
  tooltip: { label: string; x: number; y: number; details?: any } | null = null;
  selectedNode: { id: string; label: string; type: string } | null = null;
  selectedDetails: any = null;

  // Pagination
  totalCount: number = 0;
  currentPage: number = 1;
  limit: number = 20;
  totalPages: number = 0;
  private searchSubject = new Subject<string>();
  private authorSubject = new Subject<string>();

  // Audio player state
  currentlyPlaying: string | null = null;
  audioElement: HTMLAudioElement | null = null;

  constructor(
    private audioService: AudioService,
    private toast: HotToastService
  ) {
    // Debounced search
    this.searchSubject
      .pipe(
        debounceTime(500), // Waiting 500ms after user stops typing
        distinctUntilChanged() // Only emit if value actually changed
      )
      .subscribe(() => {
        this.currentPage = 1;
        this.loadPodcasts();
      });

    // Setup debounced author filter
    this.authorSubject
      .pipe(debounceTime(500), distinctUntilChanged())
      .subscribe(() => {
        this.currentPage = 1;
        this.loadPodcasts();
      });
  }

  ngOnInit() {
    this.loadPodcasts();
  }

  ngOnDestroy() {
    if (this.audioElement) {
      this.audioElement.pause();
    }
    // Complete the subjects to prevent memory leaks
    this.searchSubject.complete();
    this.authorSubject.complete();
  }

  onSearchInput() {
    this.searchSubject.next(this.searchQuery);
  }

  onAuthorInput() {
    this.authorSubject.next(this.selectedAuthor);
  }

  loadPodcasts() {
    if (!this.refreshing) {
      // Only set loading if not refreshing
      this.loading = this.currentPage === 1;
    }
    this.error = '';

    const filters = {
      title_search: this.searchQuery || undefined,
      author: this.selectedAuthor || undefined,
    };

    this.audioService
      .getAudios(this.currentPage, this.limit, filters)
      .subscribe({
        next: (response) => {
          this.totalCount = response.total_count;
          this.totalPages = Math.ceil(this.totalCount / this.limit);
          this.podcasts = response.podcasts;
          this.filteredPodcasts = [...this.podcasts];
          this.loading = false;
          this.refreshing = false;
        },
        error: (error) => {
          console.error('Error loading podcasts:', error);
          this.error = 'Failed to load podcasts. Please try again.';
          this.loading = false;
          this.refreshing = false;
          this.toast.error('Failed to load podcasts. Please try again.');
          this.podcasts = [];
          this.filteredPodcasts = [];
        },
      });
  }

  // filterPodcasts() {
  //   this.currentPage = 1;
  //   this.loadPodcasts();
  // }

  goToPage(page: number) {
    if (page >= 1 && page <= this.totalPages && page !== this.currentPage) {
      this.currentPage = page;
      this.loadPodcasts();
    }
  }

  previousPage() {
    if (this.currentPage > 1) {
      this.goToPage(this.currentPage - 1);
    }
  }

  nextPage() {
    if (this.currentPage < this.totalPages) {
      this.goToPage(this.currentPage + 1);
    }
  }

  getPageNumbers(): number[] {
    const pages: number[] = [];
    const maxVisiblePages = 5;
    let startPage = Math.max(
      1,
      this.currentPage - Math.floor(maxVisiblePages / 2)
    );
    let endPage = Math.min(this.totalPages, startPage + maxVisiblePages - 1);

    if (endPage - startPage + 1 < maxVisiblePages) {
      startPage = Math.max(1, endPage - maxVisiblePages + 1);
    }

    for (let i = startPage; i <= endPage; i++) {
      pages.push(i);
    }

    return pages;
  }

  getMinValue(a: number, b: number): number {
    return Math.min(a, b);
  }

  formatDuration(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = Math.floor(seconds % 60);
    return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
  }

  formatPublishedDate(date: string): string {
    return new Date(date).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }

  refreshPodcasts() {
    this.refreshing = true;
    this.currentPage = 1;
    this.loadPodcasts();
  }

  trackPodcastById(index: number, podcast: Podcast): string {
    return podcast.id;
  }

  togglePlayPause(podcast: Podcast) {
    if (this.currentlyPlaying === podcast.id) {
      if (this.audioElement) {
        this.audioElement.pause();
        this.currentlyPlaying = null;
      }
    } else {
      if (this.audioElement) {
        this.audioElement.pause();
      }

      this.audioElement = new Audio(podcast.embedded_audio_url);
      this.audioElement
        .play()
        .then(() => {
          this.currentlyPlaying = podcast.id;
        })
        .catch((error) => {
          console.error('Error playing audio:', error);
          this.toast.error('Failed to play audio');
        });

      this.audioElement.onended = () => {
        this.currentlyPlaying = null;
      };
    }
  }

  openDeleteModal(podcast: Podcast) {
    this.podcastToDelete = podcast;
    this.showDeleteModal = true;
  }

  closeDeleteModal() {
    this.showDeleteModal = false;
    this.podcastToDelete = null;
    this.deleting = false;
  }

  confirmDelete() {
    if (!this.podcastToDelete) return;

    this.deleting = true;

    this.audioService.deleteAudio(this.podcastToDelete.id).subscribe({
      next: (response) => {
        // Remove the deleted podcast from local arrays
        this.podcasts = this.podcasts.filter(
          (p) => p.id !== this.podcastToDelete!.id
        );
        this.filteredPodcasts = this.filteredPodcasts.filter(
          (p) => p.id !== this.podcastToDelete!.id
        );

        // Update total count
        this.totalCount--;
        this.totalPages = Math.ceil(this.totalCount / this.limit);

        // Stop playing if this was the currently playing audio
        if (this.currentlyPlaying === this.podcastToDelete!.id) {
          if (this.audioElement) {
            this.audioElement.pause();
          }
          this.currentlyPlaying = null;
        }

        // Build success message from backend response
        const detailMsg = response?.detail
          ? response.detail
          : `Audio "${this.podcastToDelete!.title}" deleted successfully`;
        const summary = response?.deletion_summary;
        let summaryMsg = '';
        if (summary) {
          const parts: string[] = [];
          if (typeof summary.transcripts_deleted === 'number') {
            parts.push(`Transcripts: ${summary.transcripts_deleted}`);
          }
          if (typeof summary.uploads_deleted === 'number') {
            parts.push(`Uploads: ${summary.uploads_deleted}`);
          }
          if (typeof summary.transcription_stats_deleted === 'number') {
            parts.push(`Transcription stats: ${summary.transcription_stats_deleted}`);
          }
          if (typeof summary.pinecone_vectors_deleted === 'number') {
            parts.push(`Pinecone vectors: ${summary.pinecone_vectors_deleted}`);
          }
          if (Array.isArray(summary.supabase_files_deleted) && summary.supabase_files_deleted.length > 0) {
            parts.push(`Supabase files: ${summary.supabase_files_deleted.length}`);
          }
          if (parts.length) {
            summaryMsg = `\n(${parts.join(' • ')})`;
          }
        }
        this.toast.success(`${detailMsg}${summaryMsg}`);
        this.closeDeleteModal();

        // If current page is empty and not the first page, go to previous page
        if (this.filteredPodcasts.length === 0 && this.currentPage > 1) {
          this.currentPage--;
          this.loadPodcasts();
        }
      },
      error: (error) => {
        console.error('Error deleting audio:', error);
        const backendDetail = error?.error?.detail;
        if (error?.status === 404 && backendDetail) {
          this.toast.error(backendDetail);
        } else if (backendDetail) {
          this.toast.error(backendDetail);
        } else {
          this.toast.error('Failed to delete audio. Please try again.');
        }
        this.deleting = false;
      },
    });
  }

  openEditModal(podcast: Podcast) {
    this.podcastToEdit = podcast;
    this.editForm = {
      title: podcast.title,
    };
    this.showEditModal = true;
  }

  closeEditModal() {
    this.showEditModal = false;
    this.podcastToEdit = null;
    this.updating = false;
    this.editForm = {
      title: '',
    };
  }

  isFormValid(): boolean {
    return (
      this.editForm.title.trim().length > 0
    );
  }

  confirmUpdate() {
    if (!this.podcastToEdit || !this.isFormValid()) return;

    this.updating = true;

    const updateData = {
      title: this.editForm.title.trim(),
    };

    this.audioService.updateAudio(this.podcastToEdit.id, updateData).subscribe({
      next: (updatedPodcast) => {
        // Update the podcast in local arrays
        const podcastIndex = this.podcasts.findIndex(
          (p) => p.id === this.podcastToEdit!.id
        );
        if (podcastIndex !== -1) {
          this.podcasts[podcastIndex] = {
            ...this.podcasts[podcastIndex],
            ...updatedPodcast,
          };
        }

        const filteredIndex = this.filteredPodcasts.findIndex(
          (p) => p.id === this.podcastToEdit!.id
        );
        if (filteredIndex !== -1) {
          this.filteredPodcasts[filteredIndex] = {
            ...this.filteredPodcasts[filteredIndex],
            ...updatedPodcast,
          };
        }

        this.toast.success(
          `Audio "${updatedPodcast.title}" updated successfully`
        );
        this.closeEditModal();
      },
      error: (error) => {
        console.error('Error updating audio:', error);
        this.toast.error('Failed to update audio. Please try again.');
        this.updating = false;
      },
    });
  }

  // Relations: open modal and fetch graph
  openRelationsModal(podcast: Podcast) {
    this.showRelationsModal = true;
    this.relationsLoading = true;
    this.relationsError = '';
    this.relationsData = null;
    this.positionedNodes = [];
    this.graphEdges = [];

    this.audioService.getAudioRelations(podcast.id).subscribe({
      next: (data) => {
        this.relationsData = data;
        // Build a simple layout
        this.buildGraphLayout(data);
        // Reset pan/zoom
        this.zoomScale = 1;
        this.panX = 0;
        this.panY = 0;
        this.updateTransform();
        this.relationsLoading = false;
      },
      error: (err) => {
        console.error('Failed to load relations', err);
        const msg = err?.error?.detail || 'Failed to load relations.';
        this.relationsError = msg;
        this.relationsLoading = false;
        this.toast.error(msg);
      },
    });
  }

  closeRelationsModal() {
    this.showRelationsModal = false;
    this.relationsData = null;
    this.positionedNodes = [];
    this.graphEdges = [];
    this.edgesDraw = [];
    this.groupRects = [];
    this.relationsError = '';
    this.relationsLoading = false;
    this.selectedNode = null;
    this.selectedDetails = null;
  }

  private buildGraphLayout(data: AudioRelationsResponse) {
    // Fixed canvas size; compute height based on max children
    const width = 1000;
    const colXs = [300, 600, 900]; // Mongo, Supabase, Pinecone
    const centerX = 600;
    const audioY = 60;
    const groupY = 180;
    const firstRowY = 300;
    const rowGap = 80;

    const nodes = data.graph.nodes as RelationsNode[];
    const edges = data.graph.edges as RelationsEdge[];

    const findNodeById = (id: string) => nodes.find((n) => n.id === id);
    const nodeMap: Record<string, { id: string; label: string; type: string; x: number; y: number; color: string; r: number }> = {};

    const colorFor = (type: string) => {
      switch (type) {
        case 'audio':
          return '#4f46e5'; // indigo
        case 'group':
          return '#0ea5e9'; // sky
        case 'supabase_file':
          return '#10b981'; // emerald
        case 'pinecone':
          return '#f59e0b'; // amber
        case 'transcripts':
          return '#22c55e'; // green
        case 'uploads':
          return '#06b6d4'; // cyan
        case 'stats':
          return '#e11d48'; // rose
        default:
          return '#64748b'; // slate
      }
    };

    const addNode = (n: RelationsNode, x: number, y: number) => {
      nodeMap[n.id] = {
        id: n.id,
        label: n.label,
        type: n.type,
        x,
        y,
        color: colorFor(n.type),
        r: n.type === 'group' ? 18 : n.type === 'audio' ? 20 : 12,
      };
    };

    // Place audio node
    const audioNode = nodes.find((n) => n.type === 'audio') || nodes[0];
    if (audioNode) addNode(audioNode, centerX, audioY);

    // Identify groups by label
    const mongoGroup = nodes.find((n) => n.type === 'group' && n.id.startsWith('mongo:'));
    const supaGroup = nodes.find((n) => n.type === 'group' && n.id.startsWith('supabase:'));
    const pineGroup = nodes.find((n) => n.type === 'group' && n.id.startsWith('pinecone:'));

    if (mongoGroup) addNode(mongoGroup, colXs[0], groupY);
    if (supaGroup) addNode(supaGroup, colXs[1], groupY);
    if (pineGroup) addNode(pineGroup, colXs[2], groupY);

    // Children under Mongo
    const mongoChildren = this.showMongo ? nodes.filter((n) => ['transcripts', 'uploads', 'stats'].includes(n.type)) : [];
    mongoChildren.forEach((n, i) => addNode(n, colXs[0], firstRowY + i * rowGap));

    // Children under Supabase
    const supaChildren = this.showSupabase ? nodes.filter((n) => n.type === 'supabase_file') : [];
    supaChildren.forEach((n, i) => addNode(n, colXs[1], firstRowY + i * rowGap));

    // Children under Pinecone
    const pineChildren = this.showPinecone ? nodes.filter((n) => n.type === 'pinecone') : [];
    pineChildren.forEach((n, i) => addNode(n, colXs[2], firstRowY + i * rowGap));

    // Compute height
    const maxRows = Math.max(mongoChildren.length, supaChildren.length, pineChildren.length);
    this.svgHeight = Math.max(400, firstRowY + Math.max(1, maxRows) * rowGap + 120);
    this.svgWidth = width;

    // Output arrays
    this.positionedNodes = Object.values(nodeMap);
    this.graphEdges = edges;
    // Precompute edge coordinates for template simplicity
    const idToPos: Record<string, { x: number; y: number }> = {};
    this.positionedNodes.forEach(n => { idToPos[n.id] = { x: n.x, y: n.y }; });
    this.edgesDraw = edges
      .map(e => {
        const a = idToPos[e.from];
        const b = idToPos[e.to];
        if (!a || !b) return null;
        return { from: e.from, to: e.to, x1: a.x, y1: a.y, x2: b.x, y2: b.y };
      })
      .filter((v): v is { from: string; to: string; x1: number; y1: number; x2: number; y2: number } => !!v);

    // Group bounding boxes (behind nodes)
    const rectWidth = 260;
    const rectHalf = rectWidth / 2;
    this.groupRects = [];
    const buildRect = (groupIdPrefix: string, colX: number, children: RelationsNode[] | { id: string }[], label: string, color: string) => {
      const hasChildren = children && children.length > 0;
      const yTop = hasChildren ? firstRowY - 50 : groupY - 60;
      const yBottom = hasChildren ? firstRowY + (Math.max(1, children.length) - 1) * rowGap + 50 : groupY + 60;
      this.groupRects.push({
        id: groupIdPrefix,
        label,
        x: colX - rectHalf,
        y: yTop,
        width: rectWidth,
        height: yBottom - yTop,
        color,
      });
    };
    if (mongoGroup) buildRect('mongo', colXs[0], mongoChildren, 'MongoDB', '#0ea5e9');
    if (supaGroup) buildRect('supabase', colXs[1], supaChildren, 'Supabase', '#10b981');
    if (pineGroup) buildRect('pinecone', colXs[2], pineChildren, 'Pinecone', '#f59e0b');
  }

  // Toggle group visibility
  toggleGroup(group: 'mongo'|'supabase'|'pinecone') {
    if (group === 'mongo') this.showMongo = !this.showMongo;
    if (group === 'supabase') this.showSupabase = !this.showSupabase;
    if (group === 'pinecone') this.showPinecone = !this.showPinecone;
    if (this.relationsData) this.buildGraphLayout(this.relationsData);
  }

  onNodeClick(n: { id: string; type: string }) {
    if (n.type === 'group') {
      if (n.id.startsWith('mongo:')) this.toggleGroup('mongo');
      else if (n.id.startsWith('supabase:')) this.toggleGroup('supabase');
      else if (n.id.startsWith('pinecone:')) this.toggleGroup('pinecone');
      return;
    }
    this.selectedNode = n as any;
    this.computeSelectedDetails();
  }

  // Pan/Zoom handlers
  onWheel(evt: WheelEvent) {
    evt.preventDefault();
    const delta = evt.deltaY > 0 ? -0.1 : 0.1;
    this.zoomScale = Math.max(0.5, Math.min(2, this.zoomScale + delta));
    this.updateTransform();
  }

  private computeSelectedDetails() {
    if (!this.relationsData || !this.selectedNode) { this.selectedDetails = null; return; }
    const id = this.selectedNode.id;
    const data = this.relationsData;
    if (id.startsWith('audio:')) {
      this.selectedDetails = {
        type: 'audio',
        title: data.audio.title,
        author: data.audio.author,
        created_at: data.audio.created_at,
        urls: data.audio.urls,
      };
    } else if (id.startsWith('transcripts:')) {
      this.selectedDetails = {
        type: 'transcripts',
        count: data.mongo.transcripts.count,
        queries: data.mongo.transcripts.queries,
      };
    } else if (id.startsWith('uploads:')) {
      this.selectedDetails = {
        type: 'uploads',
        count: data.mongo.uploads.count,
        queries: data.mongo.uploads.queries,
      };
    } else if (id.startsWith('stats:')) {
      this.selectedDetails = {
        type: 'stats',
        count: data.mongo.transcription_stats.count,
      };
    } else if (id.startsWith('supa:')) {
      const parts = id.split(':');
      const idx = Number(parts[1]);
      this.selectedDetails = {
        type: 'supabase_file',
        ...data.supabase.files[idx],
      };
    } else if (id.startsWith('pine:')) {
      const parts = id.split(':');
      const idx = Number(parts[1]);
      this.selectedDetails = {
        type: 'pinecone',
        ...data.pinecone.file_ids[idx],
      };
    } else {
      this.selectedDetails = null;
    }
  }

  onMouseDown(evt: MouseEvent) {
    this.isPanning = true;
    this.lastMouseX = evt.clientX;
    this.lastMouseY = evt.clientY;
  }

  onMouseMove(evt: MouseEvent) {
    if (!this.isPanning) return;
    const dx = evt.clientX - this.lastMouseX;
    const dy = evt.clientY - this.lastMouseY;
    this.panX += dx;
    this.panY += dy;
    this.lastMouseX = evt.clientX;
    this.lastMouseY = evt.clientY;
    this.updateTransform();
  }

  onMouseUp() {
    this.isPanning = false;
  }

  onMouseLeave() {
    this.isPanning = false;
  }

  private updateTransform() {
    this.graphTransform = `translate(${this.panX}, ${this.panY}) scale(${this.zoomScale})`;
  }

  // Tooltip handlers
  onNodeMouseEnter(n: { label: string }, evt: MouseEvent) {
    this.tooltip = { label: n.label, x: evt.clientX + 12, y: evt.clientY + 12 };
  }

  onNodeMouseLeave() {
    this.tooltip = null;
  }

  // Reset pan/zoom
  resetView() {
    this.zoomScale = 1;
    this.panX = 0;
    this.panY = 0;
    this.updateTransform();
  }

  // Toggle expanded JSON query view
  toggleQueries(which: 'transcripts'|'uploads') {
    if (which === 'transcripts') {
      this.showTranscriptQueries = !this.showTranscriptQueries;
    } else if (which === 'uploads') {
      this.showUploadQueries = !this.showUploadQueries;
    }
  }
}

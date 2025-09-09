import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface Podcast {
  id: string;
  title: string;
  description: string;
  image_url: string | null;
  embedded_audio_url: string;
  duration_seconds: number;
  author: string;
  published_date: string;
  tags: string[] | null;
  language: string;
  created_at: string;
  updated_at: string;
  views: number | null;
  likes: number | null;
  average_rating: number | null;
  is_featured: boolean;
  is_published: boolean;
}

export interface AudioResponse {
  podcasts: Podcast[];
  total_count: number;
  page: number;
  limit: number;
}

export interface AudioFilters {
  title_search?: string;
  author?: string;
}

export interface DeletionSummary {
  podcast_deleted?: boolean;
  transcripts_deleted?: number;
  uploads_deleted?: number;
  transcription_stats_deleted?: number;
  supabase_files_deleted?: string[];
  supabase_errors?: string[];
  pinecone_deleted?: boolean;
  pinecone_error?: string | null;
  pinecone_vectors_deleted?: number;
}

export interface DeleteAudioResponse {
  status?: string;
  detail: string;
  deletion_summary?: DeletionSummary;
}

export interface UpdateAudioRequest {
  title: string;
}

export interface RelationsNode {
  id: string;
  label: string;
  type: string;
}

export interface RelationsEdge {
  from: string;
  to: string;
}

export interface AudioRelationsResponse {
  audio: {
    id: string;
    title?: string;
    author?: string;
    created_at?: string;
    urls?: Record<string, string | null>;
  };
  mongo: {
    transcripts: { count: number; sample_ids?: string[]; queries?: any[] };
    uploads: { count: number; sample_ids?: string[]; queries?: any[] };
    transcription_stats: { count: number };
  };
  supabase: {
    files: Array<{ bucket?: string | null; path: string; url_field: string }>;
  };
  pinecone: {
    file_ids: Array<{ file_id: string; vectors: number; success: boolean }>;
  };
  graph: { nodes: RelationsNode[]; edges: RelationsEdge[] };
}

@Injectable({
  providedIn: 'root',
})
export class AudioService {
  private baseUrl = environment.backendApiUrl;

  constructor(private http: HttpClient) {}

  private getHeaders(): HttpHeaders {
    const token = localStorage.getItem('vEra_auth_token');
    return new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });
  }

  getAudios(
    page: number = 1,
    limit: number = 20,
    filters: AudioFilters = {},
  ): Observable<AudioResponse> {
    let params = new HttpParams()
      .set('page', page.toString())
      .set('limit', limit.toString());

    if (filters.title_search) {
      params = params.set('title_search', filters.title_search);
    }
    if (filters.author) {
      params = params.set('author', filters.author);
    }

    return this.http.get<AudioResponse>(`${this.baseUrl}/api/audios`, {
      headers: this.getHeaders(),
      params: params,
    });
  }

  deleteAudio(audioId: string): Observable<DeleteAudioResponse> {
    return this.http.delete<DeleteAudioResponse>(
      `${this.baseUrl}/api/audios/${audioId}`,
      { headers: this.getHeaders() },
    );
  }

  updateAudio(
    audioId: string,
    updateData: UpdateAudioRequest,
  ): Observable<Podcast> {
    return this.http.put<Podcast>(
      `${this.baseUrl}/api/audios/${audioId}`,
      updateData,
      { headers: this.getHeaders() },
    );
  }

  getAudioRelations(audioId: string): Observable<AudioRelationsResponse> {
    return this.http.get<AudioRelationsResponse>(
      `${this.baseUrl}/api/audios/${audioId}/relations`,
      { headers: this.getHeaders() },
    );
  }
}

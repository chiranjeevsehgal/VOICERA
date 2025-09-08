import { Injectable } from "@angular/core";
import { HttpClient, HttpHeaders } from "@angular/common/http";
import { Observable, map } from "rxjs";
import { environment } from "../../environments/environment"; // Adjust path as needed

export interface AudioFile {
  _id: string;
  title: string;
  embedded_audio_url: string;
  raw_audio_url: string;
  duration_seconds: number;
  author: string;
  published_date: string;
  language: string;
  created_at: string;
  updated_at: string;
  is_published: boolean;
  upload_id?: string;
  // Legacy fields for backward compatibility
  name?: string;
  id?: string;
  metadata?: any;
  user_data?: {
    id: string;
    user_id: string;
    file_name: string;
    file_path: string;
    file_url: string;
    metadata: any;
    created_at: string;
    updated_at: string;
    user_details?: {
      email?: string;
      full_name?: string;
    };
  };
}

export interface ApiResponse {
  files: AudioFile[];
  page?: number;
  limit?: number;
  has_next?: boolean;
}

export interface PagedPodcasts {
  podcasts: Podcast[];
  page: number;
  hasNext: boolean;
}

export interface Podcast {
  id: string;
  title: string;
  creator: string;
  imageUrl: string;
  audioFile: AudioFile;
}

export interface WordTiming {
  word: string;
  start: number;
  end: number;
  confidence?: number;
}

@Injectable({
  providedIn: "root",
})
export class PodcastService {
  private baseUrl = environment.backendApiUrl; 
  private authToken = localStorage.getItem('vEra_auth_token'); 

  constructor(private http: HttpClient) {}

  getPodcasts(): Observable<Podcast[]> {
    // Backward-compatible: fetch first page and return only items
    return this.getPodcastsPage(1).pipe(map(res => res.podcasts));
  }

  getPodcastsPage(page: number = 1): Observable<PagedPodcasts> {
    const headers = new HttpHeaders({
      'Authorization': `Bearer ${this.authToken}`,
      'Content-Type': 'application/json'
    });

    return this.http
      .get<ApiResponse>(`${this.baseUrl}/api/listAudioFiles`, {
        headers,
        params: { page: String(page) },
      })
      .pipe(
        map((response) => ({
          podcasts: this.transformApiResponseToPodcasts(response.files),
          page: response.page ?? page,
          hasNext: response.has_next === true,
        }))
      );
  }

  /**
   * Calls the backend extract API and returns transcript text and word timings.
   */
  extractTranscriptData(mp3Url: string): Observable<{ transcript: string; words: WordTiming[] }> {
    const token = localStorage.getItem('vEra_auth_token') || this.authToken || '';
    const headers = new HttpHeaders({
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    });

    return this.http
      .post<any>(`${this.baseUrl}/api/extract`, { mp3_url: mp3Url }, { headers })
      .pipe(
        map((res) => {
          const transcript = res?.results?.channels?.[0]?.alternatives?.[0]?.transcript ?? '';
          const words: WordTiming[] = res?.results?.channels?.[0]?.alternatives?.[0]?.words ?? [];
          return {
            transcript: typeof transcript === 'string' ? transcript : '',
            words: Array.isArray(words) ? words : []
          };
        })
      );
  }

  /**
   * Calls the backend extract API to fetch transcript for an MP3 URL.
   * Returns only the transcript text (empty string if not found).
   */
  extractTranscript(mp3Url: string): Observable<string> {
    const token = localStorage.getItem('vEra_auth_token') || this.authToken || '';
    const headers = new HttpHeaders({
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    });

    return this.http
      .post<any>(`${this.baseUrl}/api/extract`, { mp3_url: mp3Url }, { headers })
      .pipe(
        map((res) => {
          const transcript = res?.results?.channels?.[0]?.alternatives?.[0]?.transcript;
          return typeof transcript === 'string' ? transcript : '';
        })
      );
  }

  private transformApiResponseToPodcasts(files: AudioFile[]): Podcast[] {
    if (!Array.isArray(files)) return [];

    return files
      .filter((f): f is AudioFile => !!f && (typeof f._id === 'string' || typeof f.id === 'string'))
      .map((file) => {
        // Use new MongoDB podcast structure first, fallback to legacy
        const title = file.title || file.user_data?.file_name || file.name || 'Untitled';
        const creator = file.author || file.user_data?.user_details?.full_name || file.user_data?.user_id || 'Unknown';
        // Ensure id is always a string for the Podcast interface
        const id: string = typeof file._id === 'string' ? file._id : (file.id ?? '');

        return {
          id,
          title: title.replace(/\.mp3$/i, ''),
          creator,
          imageUrl:
            "https://res.cloudinary.com/dpbapzakz/image/upload/v1757304113/podcast_placeholder_nbkdpf.jpg",
          audioFile: file,
        };
      });
  }
}
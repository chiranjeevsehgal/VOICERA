import { Injectable } from "@angular/core";
import { HttpClient, HttpHeaders } from "@angular/common/http";
import { Observable, map } from "rxjs";
import { environment } from "../../environments/environment"; // Adjust path as needed

export interface AudioFile {
  name: string;
  id: string;
  updated_at: string;
  created_at: string;
  last_accessed_at: string;
  metadata: {
    eTag: string;
    size: number;
    mimetype: string;
    cacheControl: string;
    lastModified: string;
    contentLength: number;
    httpStatusCode: number;
  };
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
}

export interface Podcast {
  id: string;
  title: string;
  creator: string;
  imageUrl: string;
  audioFile: AudioFile;
}

@Injectable({
  providedIn: "root",
})
export class PodcastService {
  private baseUrl = environment.apiUrl; 
  private authToken = localStorage.getItem('vEra_auth_token'); 

  constructor(private http: HttpClient) {}

  getPodcasts(): Observable<Podcast[]> {
    const headers = new HttpHeaders({
      'Authorization': `Bearer ${this.authToken}`,
      'Content-Type': 'application/json'
    });

    return this.http.get<ApiResponse>(`${this.baseUrl}/api/listAudioFiles`, { headers })
      .pipe(
        map(response => this.transformApiResponseToPodcasts(response.files))
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
      .filter((f): f is AudioFile => !!f && typeof f.id === 'string')
      .map((file) => {
        const rawTitle = file.user_data?.file_name || file.name || 'Untitled';
        const title = rawTitle.replace(/\.mp3$/i, '');
        const creator =
          file.user_data?.user_details?.full_name ||
          file.user_data?.user_id ||
          'Unknown';

        return {
          id: file.id,
          title,
          creator,
          imageUrl:
            "https://media.istockphoto.com/id/1244097573/vector/headphones-minimal-icon-with-sound-waves.jpg?s=612x612&w=0&k=20&c=OvARZEMYt_CM9M9-oJmMZ3O-HtEB-CAKqpGZPSA1acM=",
          audioFile: file,
        };
      });
  }
}
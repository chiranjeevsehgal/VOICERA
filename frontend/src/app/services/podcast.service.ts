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
  user_data: {
    id: string;
    user_id: string;
    file_name: string;
    file_path: string;
    file_url: string;
    metadata: any;
    created_at: string;
    updated_at: string;
    user_details: {
      email: string;
      full_name: string;
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

  private transformApiResponseToPodcasts(files: AudioFile[]): Podcast[] {
    return files.map(file => ({
      id: file.id,
      title: file.user_data.file_name.replace('.mp3', ''), // Remove extension for title
      creator: file.user_data.user_details.full_name,
      imageUrl: "https://developers.elementor.com/docs/assets/img/elementor-placeholder-image.png",
      audioFile: file
    }));
  }
}
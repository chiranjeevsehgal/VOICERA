import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface VectorPointDto {
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

export interface VectorSpaceResponse {
  total: number;
  dimension: number;
  reduced_dimension: number;
  points: VectorPointDto[];
}

@Injectable({ providedIn: 'root' })
export class VectorVisualizationService {
  private baseUrl = environment.backendApiUrl;

  constructor(private http: HttpClient) {}

  getVectorSpace(topK: number = 1000, opts?: { fileNameContains?: string }): Observable<VectorSpaceResponse> {
    const token = localStorage.getItem('vEra_auth_token') || '';
    const headers = new HttpHeaders({
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    });

    let params = new HttpParams().set('top_k', String(topK));
    if (opts?.fileNameContains) {
      params = params.set('file_name_contains', opts.fileNameContains);
    }
    const url = `${this.baseUrl}/api/admin/vector-space`;
    return this.http.get<VectorSpaceResponse>(url, { headers, params });
  }
}

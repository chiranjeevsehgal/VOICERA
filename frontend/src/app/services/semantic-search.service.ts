// services/semantic-search.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface SearchResult {
  text: string;
  file_name: string;
  file_url: string;
  start_time: number;
  end_time: number;
  confidence: number;
  semantic_score: number;
  original_query: string;
  combined_score: number;
  keyword_score: number;
  technical_score: number;
}

export interface SearchResponse {
  query: string;
  cleaned_query: string | null;
  expanded_queries: string[];
  time_range: string | null;
  total: number;
  exact_matches: number;
  results: SearchResult[];
  search_errors: any;
  search_stats: {
    total_candidates: number;
    unique_results: number;
    queries_attempted: number;
    queries_failed: number;
    llm_reranking_applied: boolean;
    content_validation_applied: boolean;
  };
  validation_stats: {
    total_validated: number;
    relevant_count: number;
    irrelevant_count: number;
  };
  natural_language_analysis: {
    key_terms: string[];
    entities: any[];
    temporal_references: any[];
    search_intent: string;
    search_query: string;
  };
}

@Injectable({
  providedIn: 'root'
})
export class SemanticSearchService {
  private baseUrl = environment.apiUrl;
  private authToken = localStorage.getItem('vEra_auth_token');

  constructor(private http: HttpClient) {}

  searchAudio(query: string): Observable<SearchResponse> {
    const headers = new HttpHeaders({
      'Authorization': `Bearer ${this.authToken}`,
      'Content-Type': 'application/json'
    });

    const searchUrl = `${this.baseUrl}/api/search?query=${encodeURIComponent(query)}`;
    return this.http.get<SearchResponse>(searchUrl, { headers });
  }
}
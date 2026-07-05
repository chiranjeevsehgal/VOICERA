from typing import List, Dict, Optional
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from services.pinecone_service import get_embedding, index, init_pinecone
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import asyncio
from functools import partial
import logging
import math
from typing import Any, Tuple
import hashlib
import time
from services.database import transcripts_collection
from utils.logging import log_info, log_warning, log_error
try:
    from sentence_transformers import CrossEncoder
except Exception:
    CrossEncoder = None
try:
    from rank_bm25 import BM25Okapi
except Exception:
    BM25Okapi = None
try:
    from nltk.stem import SnowballStemmer
    from nltk.corpus import wordnet as wn
    NLTK_AVAILABLE = True
except Exception:
    NLTK_AVAILABLE = False
try:
    from nltk.tokenize import sent_tokenize
    NLTK_SENT_TOKENIZE_AVAILABLE = True
except Exception:
    NLTK_SENT_TOKENIZE_AVAILABLE = False
try:
    from rapidfuzz import fuzz
    RAPIDFUZZ_AVAILABLE = True
except Exception:
    RAPIDFUZZ_AVAILABLE = False
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedSearch:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EnhancedSearch, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            logger.info('Initializing EnhancedSearch instance...')
            self.chunk_size = 100
            self.chunk_overlap = 50
            self.min_chunk_size = 30
            self.max_parallel_tasks = 10
            self.batch_size = 50
            self.context_window = 2
            self.cross_encoder_model_name = 'cross-encoder/ms-marco-MiniLM-L-6-v2'
            self.cross_encoder = None
            self.enable_mmr = True
            self.mmr_lambda = 0.6
            self.rrf_k = 60
            self.bm25 = None
            self._bm25_tokens: List[List[str]] = []
            self._bm25_docs: List[Dict[str, Any]] = []
            self._bm25_ready: bool = False
            self._bm25_last_built: float = 0.0
            self._embedding_cache: Dict[str, List[float]] = {}
            self.stemmer = SnowballStemmer('english') if NLTK_AVAILABLE else None
            if not index:
                logger.info('Initializing Pinecone connection...')
                init_pinecone()
                if not index:
                    logger.warning('Failed to initialize Pinecone connection')
            self._initialized = True
            logger.info('EnhancedSearch initialization complete')

    def create_semantic_chunks(self, text: str) -> List[Dict]:
        """
        Create chunks based on sentence boundaries with token-based size and overlap.
        Falls back to regex sentence splitting when NLTK is not available.
        """
        sentences = self._split_sentences(text)
        chunks: List[Dict] = []
        current_sentences: List[str] = []
        current_tokens = 0
        for sentence in sentences:
            sent_tokens = self._estimate_token_count(sentence)
            if current_tokens + sent_tokens > self.chunk_size and current_tokens >= self.min_chunk_size:
                chunk_text = ' '.join(current_sentences).strip()
                if chunk_text:
                    chunks.append({'text': chunk_text, 'length': current_tokens})
                if self.chunk_overlap > 0 and current_sentences:
                    overlap_sentences: List[str] = []
                    overlap_tokens = 0
                    for s in reversed(current_sentences):
                        t = self._estimate_token_count(s)
                        if overlap_tokens + t > self.chunk_overlap and overlap_sentences:
                            break
                        overlap_sentences.append(s)
                        overlap_tokens += t
                    current_sentences = list(reversed(overlap_sentences))
                    current_tokens = overlap_tokens
                else:
                    current_sentences = []
                    current_tokens = 0
            current_sentences.append(sentence)
            current_tokens += sent_tokens
        remainder_text = ' '.join(current_sentences).strip()
        if remainder_text and (current_tokens >= self.min_chunk_size or not chunks):
            chunks.append({'text': remainder_text, 'length': current_tokens})
        return chunks

    async def hybrid_search(self, query: str, limit: int=10, filter_dict: Optional[Dict]=None, original_query: Optional[str]=None, debug: bool=False) -> List[Dict]:
        """
        Perform hybrid search with improved context awareness and relevance scoring

        Args:
            query: The search query (may be expanded/processed)
            limit: Maximum number of results to return
            filter_dict: Optional filters to apply
            original_query: The original user query for technical term scoring
            debug: Flag to return diagnostics
        """
        try:
            query_for_tech_scoring = original_query or query
            if not index:
                logger.info('Reinitializing Pinecone connection...')
                if not init_pinecone():
                    logger.error('Could not initialize Pinecone connection')
                    return {'results': [], 'diagnostics': {'error': 'Pinecone connection failed'}} if debug else []
            logger.info(f'Performing hybrid search with query: {query}, original query: {query_for_tech_scoring}')
            if filter_dict:
                logger.info(f'Using filters: {filter_dict}')
            expansions = self._expand_query_multi(query_for_tech_scoring)
            if query_for_tech_scoring not in expansions:
                expansions.insert(0, query_for_tech_scoring)
            total_target = min(max(limit * 10, 100), 200)
            per_expansion_k = max(10, total_target // max(1, len(expansions)))
            candidate_map: Dict[str, Dict[str, Any]] = {}
            for q_exp in expansions:
                try:
                    q_emb = self._embed(q_exp)
                except Exception:
                    q_emb = self._embed(query_for_tech_scoring)
                sem_results = await self._semantic_search(query_embedding=q_emb, limit=per_expansion_k, filter_dict=filter_dict, include_values=self.enable_mmr)
                for r in sem_results:
                    r['original_query'] = query_for_tech_scoring
                    r['expansion'] = q_exp
                    rid = r.get('id') or f"{r.get('file_name', '')}|{r.get('start_time', '')}|{hash(r.get('text', ''))}"
                    if rid not in candidate_map:
                        candidate_map[rid] = r
                    elif r.get('semantic_score', 0) > candidate_map[rid].get('semantic_score', 0):
                        candidate_map[rid] = r
            semantic_results = list(candidate_map.values())
            logger.info(f'Candidate pool size after expansions: {len(semantic_results)}')
            if not semantic_results:
                logger.warning('No semantic results found, check Pinecone connection and index content')
                return {'results': [], 'diagnostics': {'candidate_pool_size': 0}} if debug else []
            fused_candidates = semantic_results
            try:
                if BM25Okapi is not None:
                    await self._ensure_bm25_index()
                    sparse_results = await self._bm25_search(query_for_tech_scoring, top_k=total_target)
                    if sparse_results:
                        fused_candidates = self._rrf_fuse(semantic_results, sparse_results, k=self.rrf_k)
                        logger.info(f'Fused candidates (RRF): {len(fused_candidates)}')
                else:
                    logger.info('rank_bm25 not available; skipping sparse retrieval')
            except Exception as e:
                logger.error(f'Sparse retrieval fusion error: {str(e)}')
                fused_candidates = semantic_results
            query_terms = self._extract_key_terms(query)
            keyword_results = await self._context_aware_keyword_search(query=query, query_terms=query_terms, texts=[r.get('text', '') for r in fused_candidates], metadata=[{'file_name': r.get('file_name'), 'start_time': r.get('start_time'), 'end_time': r.get('end_time')} for r in fused_candidates])
            _combined = await self._combine_results_with_context(semantic_results=fused_candidates, keyword_scores=keyword_results, weights={'semantic': 0.5, 'keyword': 0.5}, debug=debug)
            if debug:
                combined_results, combine_diag = _combined
            else:
                combined_results = _combined
            combined_results = await self._rerank_with_cross_encoder(query_for_tech_scoring, combined_results, top_k=min(100, len(combined_results)))
            try:
                if self.enable_mmr:
                    diverse_results = self._apply_mmr_embeddings(results=combined_results, query_embedding=self._embed(query_for_tech_scoring), max_results=limit, lambda_mult=self.mmr_lambda)
                else:
                    raise ValueError('MMR disabled')
            except Exception as e:
                logger.error(f'Error in MMR diversification: {str(e)}')
                logger.info('Falling back to lexical diversity filter')
                try:
                    diverse_results = await self._apply_context_aware_diversity_filter(results=combined_results, similarity_threshold=0.85, max_results=limit)
                except Exception:
                    diverse_results = combined_results[:limit]
            final_results = diverse_results[:limit]
            if debug:
                diag: Dict[str, Any] = {'candidate_pool_size': len(semantic_results), 'fused_candidates': len(fused_candidates), 'post_combine_count': len(combined_results), 'final_count': len(final_results)}
                try:
                    if combine_diag:
                        diag['context_gate'] = combine_diag
                except Exception:
                    pass
                return {'results': final_results, 'diagnostics': diag}
            return final_results
        except Exception as e:
            logger.error(f'Error in hybrid search: {str(e)}')
            return {'results': [], 'diagnostics': {'error': str(e)}} if debug else []

    def _extract_key_terms(self, query: str) -> Dict[str, float]:
        """
        Extract and weight key terms from query
        """
        cleaned_query = re.sub('[^\\w\\s]', ' ', query.lower())
        words = cleaned_query.split()
        term_weights = {}
        for word in words:
            if len(word) > 2 and word not in self._get_stopwords():
                term_weights[word] = term_weights.get(word, 0) + 1.0
                if word in ['why', 'how', 'what', 'when', 'where', 'who']:
                    term_weights[word] *= 1.2
                elif word.endswith(('ing', 'ed', 'ion', 'ment')):
                    term_weights[word] *= 1.3
                elif word in ['not', 'never', 'no']:
                    term_weights[word] *= 1.5
        return term_weights

    async def _context_aware_keyword_search(self, query: str, query_terms: Dict[str, float], texts: List[str], metadata: List[Dict]) -> List[float]:
        """
        Perform keyword search with context awareness and return scores aligned
        to the original semantic_results/texts order.
        """
        aligned_scores = [0.0] * len(texts)
        entries = [(i, texts[i] or '', metadata[i] if i < len(metadata) else {}) for i in range(len(texts))]
        entries.sort(key=lambda x: (str(x[2].get('file_name') or ''), x[2].get('start_time', 0)))
        current_file = None
        group: List[tuple] = []

        def flush_group(g: List[tuple]):
            for idx_in_group, (orig_idx, text, meta) in enumerate(g):
                text_lower = (text or '').lower()
                text_tokens = self._tokenize(text_lower)
                term_score = 0.0
                for term, weight in query_terms.items():
                    if self._term_in_text(term, text_tokens, text_lower):
                        term_score += weight
                context_bonus = 0.0
                start_idx = max(0, idx_in_group - self.context_window)
                end_idx = min(len(g), idx_in_group + self.context_window + 1)
                for j in range(start_idx, end_idx):
                    if j == idx_in_group:
                        continue
                    neighbor_text_lower = (g[j][1] or '').lower()
                    neighbor_tokens = self._tokenize(neighbor_text_lower)
                    distance_factor = 1 / (abs(j - idx_in_group) + 1)
                    for term, weight in query_terms.items():
                        if self._term_in_text(term, neighbor_tokens, neighbor_text_lower):
                            context_bonus += weight * distance_factor * 0.5
                aligned_scores[orig_idx] = term_score + context_bonus
        for entry in entries:
            file_name = entry[2].get('file_name')
            if current_file is None:
                current_file = file_name
                group = [entry]
            elif file_name == current_file:
                group.append(entry)
            else:
                flush_group(group)
                current_file = file_name
                group = [entry]
        if group:
            flush_group(group)
        return aligned_scores

    def _group_by_context(self, texts: List[str], metadata: List[Dict]) -> List[List[str]]:
        """
        Group texts by file and temporal proximity
        """
        sorted_pairs = sorted(zip(texts, metadata), key=lambda x: (x[1]['file_name'], x[1].get('start_time', 0)))
        groups = []
        current_group = []
        current_file = None
        for text, meta in sorted_pairs:
            if current_file != meta['file_name']:
                if current_group:
                    groups.append(current_group)
                current_group = [text]
                current_file = meta['file_name']
            else:
                current_group.append(text)
        if current_group:
            groups.append(current_group)
        return groups

    def _calculate_context_bonus(self, text: str, group: List[str], query_terms: Dict[str, float]) -> float:
        """
        Calculate context bonus based on term presence in nearby chunks
        """
        text_idx = group.index(text)
        context_bonus = 0
        start_idx = max(0, text_idx - self.context_window)
        end_idx = min(len(group), text_idx + self.context_window + 1)
        for i in range(start_idx, end_idx):
            if i != text_idx:
                context_text = group[i].lower()
                distance_factor = 1 / (abs(i - text_idx) + 1)
                for term, weight in query_terms.items():
                    if term in context_text:
                        context_bonus += weight * distance_factor * 0.5
        return context_bonus

    def _get_stopwords(self) -> set:
        """Get enhanced stopwords list"""
        return frozenset({'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'were', 'will', 'with', 'said', 'say', 'says', 'she', 'he', 'they', 'we', 'you', 'yeah', 'okay', 'ok', 'um', 'uh', 'like', 'well', 'right', 'oh', 'hi', 'hello', 'thanks', 'thank', 'please', 'just'})

    async def _semantic_search(self, query_embedding: List[float], limit: int, filter_dict: Optional[Dict]=None, include_values: bool=False) -> List[Dict]:
        """
        Perform semantic search using Pinecone with improved error handling
        """
        try:
            if not index:
                from services.pinecone_service import init_pinecone
                if not init_pinecone():
                    log_error('Could not initialize Pinecone', 'enhanced_search')
                    return []
            results = index.query(vector=query_embedding, top_k=limit, include_metadata=True, include_values=include_values, filter=filter_dict)
            if not results or not results.get('matches'):
                log_info(f'No results found for query (limit: {limit})', 'enhanced_search', {'query': query_embedding[:5] if query_embedding else None, 'limit': limit})
                return []
            return [{**match['metadata'], 'id': match.get('id'), 'semantic_score_raw': match.get('score', 0.0), 'semantic_score': match.get('score', 0.0), 'text': match.get('metadata', {}).get('text', ''), 'vector': match.get('values') if include_values else None} for match in results.get('matches', [])]
        except Exception as e:
            log_error(f'Error in semantic search: {str(e)}', 'enhanced_search', {'error': str(e)})
            return []

    async def _batched_keyword_search(self, query: str, texts: List[str]) -> List[float]:
        """
        Perform keyword-based search using batched processing
        """
        query_terms = set(self._normalize_text(query))
        scores = []
        batch_size = self.batch_size
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            with ThreadPoolExecutor(max_workers=self.max_parallel_tasks) as executor:
                batch_scores = list(executor.map(partial(self._calculate_keyword_score, query_terms=query_terms), batch))
            scores.extend(batch_scores)
        return scores

    def _calculate_keyword_score(self, text: str, query_terms: set) -> float:
        """
        Calculate keyword score for a single text
        """
        text_terms = set(self._normalize_text(text))
        intersection = len(query_terms & text_terms)
        union = len(query_terms | text_terms)
        term_freq_score = sum((text.lower().count(term.lower()) for term in query_terms)) / len(text.split())
        return (intersection / union if union > 0 else 0) + term_freq_score

    async def _combine_results_batched(self, semantic_results: List[Dict], keyword_scores: List[float], weights: Dict[str, float]) -> List[Dict]:
        """
        Combine semantic and keyword search results with batched processing
        """
        combined_results = []
        max_semantic = max((r['semantic_score'] for r in semantic_results)) if semantic_results else 1
        max_keyword = max(keyword_scores) if keyword_scores else 1
        batch_size = self.batch_size
        for i in range(0, len(semantic_results), batch_size):
            batch_semantic = semantic_results[i:i + batch_size]
            batch_keyword = keyword_scores[i:i + batch_size]
            batch_combined = []
            for result, keyword_score in zip(batch_semantic, batch_keyword):
                normalized_semantic = result['semantic_score'] / max_semantic
                normalized_keyword = keyword_score / max_keyword
                combined_score = weights['semantic'] * normalized_semantic + weights['keyword'] * normalized_keyword
                batch_combined.append({**result, 'combined_score': combined_score, 'keyword_score': keyword_score})
            combined_results.extend(batch_combined)
        combined_results.sort(key=lambda x: x['combined_score'], reverse=True)
        return combined_results

    async def _apply_context_aware_diversity_filter(self, results: List[Dict], similarity_threshold: float=0.85, max_results: int=10) -> List[Dict]:
        """
        Apply diversity filtering with context awareness
        """
        if not results:
            return []
        diverse_results = [results[0]]
        candidates = results[1:]
        while len(diverse_results) < max_results and candidates:
            most_diverse_candidate = None
            max_min_distance = -1
            for candidate in candidates:
                min_distance = float('inf')
                for selected in diverse_results:
                    similarity = self._calculate_text_similarity(candidate.get('text', ''), selected.get('text', ''))
                    distance = 1 - similarity
                    min_distance = min(min_distance, distance)
                if min_distance > max_min_distance:
                    max_min_distance = min_distance
                    most_diverse_candidate = candidate
            if most_diverse_candidate and max_min_distance > 1 - similarity_threshold:
                diverse_results.append(most_diverse_candidate)
                candidates.remove(most_diverse_candidate)
            else:
                break
        return diverse_results

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate semantic similarity between two texts
        """
        if not text1 or not text2:
            return 0.0
        words1 = set(self._normalize_text(text1))
        words2 = set(self._normalize_text(text2))
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        return intersection / union if union > 0 else 0.0

    def _normalize_text(self, text: str) -> List[str]:
        """
        Normalize text for comparison
        """
        words = text.lower().split()
        return [w for w in words if w not in self._get_stopwords() and len(w) > 2]

    async def _combine_results_with_context(self, semantic_results: List[Dict], keyword_scores: List[float], weights: Dict[str, float], debug: bool=False) -> List[Dict]:
        """
        Combine semantic and keyword results with context awareness and technical term scoring
        """
        try:
            if not semantic_results:
                log_warning('No semantic results found', 'enhanced_search')
                return ([], {'note': 'no_semantic_results', 'skip_count': 0}) if debug else []
            if not keyword_scores:
                log_warning('No keyword scores found', 'enhanced_search')
                return (semantic_results, {'note': 'no_keyword_scores', 'skip_count': 0}) if debug else semantic_results
            tech_scorer = TechnicalTermsScorer()
            max_semantic = max((r.get('semantic_score', 0) for r in semantic_results))
            max_keyword = max(keyword_scores) if keyword_scores else 1
            original_query = semantic_results[0].get('original_query', '') if semantic_results else ''
            cleaned_query = re.sub('[^\\w\\s]', ' ', original_query.lower()).strip()
            base_query_terms = [w for w in cleaned_query.split() if w and w not in self._get_stopwords()]
            short_query = len(base_query_terms) <= 2
            has_specific_token = any((len(t) >= 7 for t in base_query_terms))
            if short_query or has_specific_token:
                dyn_weights = {'semantic': 0.3, 'keyword': 0.5, 'technical': 0.2}
            else:
                dyn_weights = {'semantic': 0.4, 'keyword': 0.3, 'technical': 0.3}
            combined_results = []
            skip_count = 0
            for result, keyword_score in zip(semantic_results, keyword_scores):
                if 'text' not in result:
                    log_warning(f'Missing text field in result: {result}', 'enhanced_search', {'result_keys': list(result.keys()) if isinstance(result, dict) else None})
                    continue
                raw_sem = result.get('semantic_score', 0)
                normalized_semantic = raw_sem / max_semantic if max_semantic else 0
                normalized_keyword = keyword_score / max_keyword if max_keyword else 0
                raw_tech_score = tech_scorer.calculate_technical_score(text=result.get('text', ''), query=result.get('original_query', ''))
                tech_score = max(0.0, min(1.0, raw_tech_score - 1.0))
                combined_score = dyn_weights['semantic'] * normalized_semantic + dyn_weights['keyword'] * normalized_keyword + dyn_weights['technical'] * tech_score
                if (short_query or has_specific_token) and normalized_keyword == 0:
                    combined_score *= 0.2
                if short_query or has_specific_token:
                    raw_semantic = result.get('semantic_score', 0.0)
                    text_lower = result.get('text', '').lower()
                    has_query_token_in_text = any((t in text_lower for t in base_query_terms))
                    exp = result.get('expansion', '') or ''
                    exp_clean = re.sub('[^\\w\\s]', ' ', exp.lower()).strip()
                    exp_terms = [w for w in exp_clean.split() if w and w not in self._get_stopwords()]
                    has_expansion_token_in_text = any((t in text_lower for t in exp_terms))
                    if normalized_keyword == 0 and tech_score <= 0.01 and (normalized_semantic < 0.15 and raw_semantic < 0.15) and (not (has_query_token_in_text or has_expansion_token_in_text)):
                        skip_count += 1
                        continue
                combined_result = {**result, 'combined_score': combined_score, 'keyword_score': normalized_keyword, 'semantic_score': normalized_semantic, 'semantic_score_raw': raw_sem if 'semantic_score_raw' not in result else result.get('semantic_score_raw'), 'technical_score': tech_score, 'weights_used': {'semantic': dyn_weights['semantic'], 'keyword': dyn_weights['keyword'], 'technical': dyn_weights['technical']}}
                combined_results.append(combined_result)
            combined_results.sort(key=lambda x: x['combined_score'], reverse=True)
            log_info(f'Combined {len(combined_results)} results', 'enhanced_search', {'result_count': len(combined_results), 'top_score': combined_results[0]['combined_score'] if combined_results else None, 'top_technical_score': combined_results[0]['technical_score'] if combined_results else None})
            try:
                logger.info(f'Context gate skipped {skip_count} results (short_or_specific={short_query or has_specific_token}) out of {len(semantic_results)} candidates')
            except Exception:
                pass
            if debug:
                diag = {'skip_count': skip_count, 'short_or_specific': bool(short_query or has_specific_token), 'candidates': len(semantic_results), 'kept': len(combined_results)}
                return (combined_results, diag)
            return combined_results
        except Exception as e:
            log_error(f'Error combining results: {str(e)}', 'enhanced_search', {'error': str(e)})
            return (semantic_results, {'note': 'combine_error', 'error': str(e)}) if debug else semantic_results

    def _embed(self, text: str) -> List[float]:
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        vec = get_embedding(text, task_type='RETRIEVAL_QUERY')
        self._embedding_cache[text] = vec
        return vec

    def _tokenize(self, text: str) -> List[str]:
        tokens = re.findall('[a-z0-9]+', text.lower())
        if self.stemmer:
            try:
                tokens = [self.stemmer.stem(t) for t in tokens]
            except Exception:
                pass
        return tokens

    def _split_sentences(self, text: str) -> List[str]:
        """Robust sentence splitter with safe fallback.
        Uses NLTK's sent_tokenize if available; otherwise falls back to regex.
        """
        try:
            if NLTK_SENT_TOKENIZE_AVAILABLE:
                sents = sent_tokenize(text)
                return [s.strip() for s in sents if s and s.strip()]
        except Exception:
            pass
        sents = re.split('(?<=[.!?])\\s+', text)
        return [s.strip() for s in sents if s and s.strip()]

    def _estimate_token_count(self, text: str) -> int:
        """Estimate token count for chunk sizing without external dependencies.
        Approximate tokens as word and punctuation groups.
        """
        if not text:
            return 0
        return len(re.findall('\\w+|[^\\w\\s]', text, flags=re.UNICODE))

    def _term_in_text(self, term: str, tokens: List[str], text_lower: str) -> bool:
        term_tokens = re.findall('[a-z0-9]+', term.lower())
        if self.stemmer:
            try:
                term_tokens = [self.stemmer.stem(t) for t in term_tokens]
            except Exception:
                pass
        if not term_tokens:
            return False
        ok = all((t in tokens for t in term_tokens))
        if ok:
            return True
        if RAPIDFUZZ_AVAILABLE and len(term) >= 4:
            try:
                return fuzz.partial_ratio(term, text_lower) >= 90
            except Exception:
                return term in text_lower
        return term in text_lower

    async def _rerank_with_cross_encoder(self, query: str, results: List[Dict], top_k: int=100) -> List[Dict]:
        if not results:
            return results
        if CrossEncoder is None:
            return results
        try:
            if self.cross_encoder is None:
                logger.info(f'Loading cross-encoder model: {self.cross_encoder_model_name}')
                self.cross_encoder = CrossEncoder(self.cross_encoder_model_name)
        except Exception as e:
            logger.error(f'Failed to load cross-encoder: {str(e)}')
            return results
        base_sorted = sorted(results, key=lambda r: r.get('combined_score', r.get('semantic_score', 0)), reverse=True)
        rerank_subset = base_sorted[:top_k]
        pairs = [(query, r.get('text', '')) for r in rerank_subset]
        try:
            scores = self.cross_encoder.predict(pairs)
        except Exception as e:
            logger.error(f'Cross-encoder inference failed: {str(e)}')
            return results
        if isinstance(scores, list):
            scores = np.array(scores, dtype=float)
        min_s, max_s = (float(np.min(scores)), float(np.max(scores)))
        denom = max_s - min_s if max_s - min_s > 1e-08 else 1.0
        norm_scores = (scores - min_s) / denom
        for r, s in zip(rerank_subset, norm_scores):
            r['rerank_score'] = float(s)
            base = r.get('combined_score', r.get('semantic_score', 0.0))
            r['combined_score'] = 0.6 * float(s) + 0.4 * float(base)
        return sorted(results, key=lambda r: r.get('combined_score', r.get('semantic_score', 0)), reverse=True)

    def _apply_mmr_embeddings(self, results: List[Dict], query_embedding: List[float], max_results: int=10, lambda_mult: float=0.6) -> List[Dict]:
        if not results:
            return []
        vectors = []
        valid_results = []
        for r in results:
            v = r.get('vector')
            if v is not None:
                vectors.append(np.array(v, dtype=float))
                valid_results.append(r)
        if not vectors:
            return results[:max_results]
        doc_matrix = np.vstack(vectors)
        q = np.array(query_embedding, dtype=float)
        q_sim = cosine_similarity(doc_matrix, q.reshape(1, -1)).reshape(-1)
        selected = []
        selected_indices: List[int] = []
        candidate_indices = list(range(len(valid_results)))
        while candidate_indices and len(selected) < max_results:
            if not selected_indices:
                best_idx = int(np.argmax(q_sim[candidate_indices]))
                chosen = candidate_indices[best_idx]
            else:
                mmr_scores = []
                for idx in candidate_indices:
                    sim_to_selected = 0.0
                    for sidx in selected_indices:
                        sim = float(cosine_similarity(doc_matrix[idx].reshape(1, -1), doc_matrix[sidx].reshape(1, -1))[0][0])
                        sim_to_selected = max(sim_to_selected, sim)
                    mmr = lambda_mult * q_sim[idx] - (1 - lambda_mult) * sim_to_selected
                    mmr_scores.append(mmr)
                best_local = int(np.argmax(mmr_scores))
                chosen = candidate_indices[best_local]
            selected.append(valid_results[chosen])
            selected_indices.append(chosen)
            candidate_indices.remove(chosen)
        if len(selected) < max_results:
            selected_ids = {id(s) for s in selected}
            for r in sorted(results, key=lambda x: x.get('combined_score', x.get('semantic_score', 0.0)), reverse=True):
                if id(r) not in selected_ids:
                    selected.append(r)
                    selected_ids.add(id(r))
                if len(selected) >= max_results:
                    break
        return selected

    def _fusion_id(self, item: Dict) -> str:
        """Create a stable fusion id across modalities for RRF merging."""
        text = (item.get('text') or '').strip()
        st = item.get('start_time')
        fn = item.get('file_name') or ''
        base = f'{fn}|{st}|{text}'
        return hashlib.sha1(base.encode('utf-8', errors='ignore')).hexdigest()

    async def _ensure_bm25_index(self, rebuild_interval_sec: int=3600) -> None:
        """Build or refresh BM25 index from transcripts_collection segments/content."""
        if BM25Okapi is None:
            return
        now = time.time()
        if self._bm25_ready and now - self._bm25_last_built < rebuild_interval_sec and (self.bm25 is not None):
            return
        logger.info('Building BM25 sparse index from transcripts...')
        try:
            cursor = transcripts_collection.find({}, projection={'segments': 1, 'content': 1, 'podcast_id': 1})
            docs = await cursor.to_list(length=5000)
        except Exception as e:
            logger.error(f'Failed to read transcripts for BM25: {str(e)}')
            return
        tokens_list: List[List[str]] = []
        docs_meta: List[Dict[str, Any]] = []
        count = 0
        for d in docs:
            segs = d.get('segments') or []
            if isinstance(segs, list) and segs:
                for seg in segs:
                    text = seg.get('text') or seg.get('transcript') or ''
                    if not text:
                        continue
                    toks = self._tokenize(text)
                    if not toks:
                        continue
                    meta = {'text': text, 'start_time': seg.get('start_time') or seg.get('start') or seg.get('begin'), 'end_time': seg.get('end_time') or seg.get('end') or seg.get('stop'), 'file_name': seg.get('file_name') or d.get('file_name'), 'podcast_id': d.get('podcast_id')}
                    tokens_list.append(toks)
                    docs_meta.append(meta)
                    count += 1
            else:
                content = d.get('content') or ''
                if not content:
                    continue
                for ch in self.create_semantic_chunks(content):
                    text = ch.get('text', '')
                    if not text:
                        continue
                    toks = self._tokenize(text)
                    if not toks:
                        continue
                    meta = {'text': text, 'start_time': None, 'end_time': None, 'file_name': None, 'podcast_id': d.get('podcast_id')}
                    tokens_list.append(toks)
                    docs_meta.append(meta)
                    count += 1
        if not tokens_list:
            logger.warning('No documents available for BM25 index')
            return
        try:
            self.bm25 = BM25Okapi(tokens_list)
            self._bm25_tokens = tokens_list
            self._bm25_docs = docs_meta
            self._bm25_ready = True
            self._bm25_last_built = time.time()
            logger.info(f'BM25 index built over {len(tokens_list)} chunks')
        except Exception as e:
            logger.error(f'Failed to build BM25 index: {str(e)}')

    async def _bm25_search(self, query: str, top_k: int=100) -> List[Dict]:
        """Search BM25 index and return top-k sparse results with metadata."""
        if BM25Okapi is None or not self._bm25_ready or self.bm25 is None:
            return []
        q_tokens = self._tokenize(query)
        if not q_tokens:
            return []
        try:
            scores = self.bm25.get_scores(q_tokens)
            idxs = np.argsort(scores)[::-1][:top_k]
            results: List[Dict] = []
            for i in idxs:
                meta = self._bm25_docs[int(i)]
                r = {**meta, 'bm25_score': float(scores[int(i)]), 'semantic_score': meta.get('semantic_score', 0.0), 'vector': None}
                results.append(r)
            return results
        except Exception as e:
            logger.error(f'BM25 search failed: {str(e)}')
            return []

    def _rrf_fuse(self, dense: List[Dict], sparse: List[Dict], k: int=60) -> List[Dict]:
        """Reciprocal Rank Fusion across dense and sparse results using stable fusion ids."""
        dense_sorted = sorted(dense, key=lambda x: x.get('semantic_score', 0.0), reverse=True)
        sparse_sorted = sorted(sparse, key=lambda x: x.get('bm25_score', 0.0), reverse=True)
        rrf_scores: Dict[str, float] = {}
        fused: Dict[str, Dict] = {}
        for rank, item in enumerate(dense_sorted, start=1):
            fid = self._fusion_id(item)
            rrf_scores[fid] = rrf_scores.get(fid, 0.0) + 1.0 / (k + rank)
            if fid not in fused:
                fused[fid] = item
        for rank, item in enumerate(sparse_sorted, start=1):
            fid = self._fusion_id(item)
            rrf_scores[fid] = rrf_scores.get(fid, 0.0) + 1.0 / (k + rank)
            if fid in fused:
                fused[fid]['bm25_score'] = item.get('bm25_score', fused[fid].get('bm25_score', 0.0))
            else:
                fused[fid] = item
        fused_list = list(fused.values())
        fused_list.sort(key=lambda x: rrf_scores.get(self._fusion_id(x), 0.0), reverse=True)
        for it in fused_list:
            it['rrf_score'] = rrf_scores.get(self._fusion_id(it), 0.0)
        return fused_list

    def _expand_query_multi(self, query: str, max_synonyms: int=3) -> List[str]:
        expansions = [query]
        if not NLTK_AVAILABLE:
            return expansions
        try:
            tokens = re.findall('[a-zA-Z0-9]+', query)
            syns: List[str] = []
            for t in tokens:
                synsets = wn.synsets(t)
                for ss in synsets[:2]:
                    for lemma in ss.lemmas()[:2]:
                        cand = lemma.name().replace('_', ' ')
                        if cand.lower() != t.lower() and cand.lower() not in (s.lower() for s in syns):
                            syns.append(cand)
                            if len(syns) >= max_synonyms:
                                break
                    if len(syns) >= max_synonyms:
                        break
                if len(syns) >= max_synonyms:
                    break
            for s in syns:
                expansions.append(query + ' ' + s)
        except Exception:
            pass
        seen = set()
        unique_exp = []
        for e in expansions:
            if e not in seen:
                unique_exp.append(e)
                seen.add(e)
        return unique_exp

class TechnicalTermsScorer:

    def __init__(self):
        self.common_words = {'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'were', 'will', 'with', 'about', 'above', 'after', 'again', 'all', 'also', 'am', 'any', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'can', 'did', 'do', 'does', 'doing', 'down', 'during', 'each', 'few', 'further', 'had', 'have', 'having', 'her', 'here', 'hers', 'herself', 'him', 'himself', 'his', 'how', 'i', 'if', 'into', 'just', 'me', 'more', 'most', 'my', 'myself', 'no', 'nor', 'not', 'now', 'or', 'other', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', 'she', 'should', 'so', 'some', 'such', 'than', 'then', 'there', 'these', 'they', 'this', 'those', 'through', 'too', 'under', 'until', 'up', 'very', 'we', 'what', 'when', 'where', 'which', 'while', 'who', 'whom', 'why', 'you', 'your', 'yours', 'yourself', 'yourselves'}

    def _extract_significant_terms(self, text: str) -> set:
        """
        Extract potentially significant terms from text by:
        1. Removing common words
        2. Identifying multi-word phrases
        3. Finding specialized/longer terms
        """
        text_lower = text.lower()
        words = text_lower.split()
        significant_terms = {word for word in words if word not in self.common_words and len(word) > 3}
        for i in range(len(words) - 1):
            phrase = f'{words[i]} {words[i + 1]}'
            if not any((word in self.common_words for word in phrase.split())):
                significant_terms.add(phrase)
            if i < len(words) - 2:
                phrase = f'{words[i]} {words[i + 1]} {words[i + 2]}'
                if not any((word in self.common_words for word in phrase.split())):
                    significant_terms.add(phrase)
        return significant_terms

    def calculate_technical_score(self, text: str, query: str) -> float:
        """
        Calculate relevance score based on shared significant terms between query and text
        """
        if not text or not query:
            return 0.0
        query_terms = self._extract_significant_terms(query)
        text_terms = self._extract_significant_terms(text)
        if not query_terms or not text_terms:
            return 1.0
        matching_terms = query_terms & text_terms
        if not matching_terms:
            return 1.0
        overlap_ratio = len(matching_terms) / len(query_terms)
        base_score = 1.0 + overlap_ratio * 0.5
        long_term_bonus = sum((0.1 for term in matching_terms if len(term.split()) > 1))
        proximity_bonus = self._calculate_proximity_bonus(text, matching_terms)
        density_bonus = len(matching_terms) / len(text.split()) * 0.3
        final_score = base_score + long_term_bonus + proximity_bonus + density_bonus
        return min(final_score, 2.0)

    def _calculate_proximity_bonus(self, text: str, matching_terms: set) -> float:
        """
        Calculate bonus score based on how close matching terms appear to each other
        """
        if len(matching_terms) < 2:
            return 0.0
        words = text.lower().split()
        term_positions = []
        for i, word in enumerate(words):
            for term in matching_terms:
                if term.startswith(word):
                    term_words = term.split()
                    if i + len(term_words) <= len(words):
                        if ' '.join(words[i:i + len(term_words)]) == term:
                            term_positions.append(i)
        if not term_positions or len(term_positions) < 2:
            return 0.0
        min_distance = float('inf')
        for i in range(len(term_positions) - 1):
            distance = term_positions[i + 1] - term_positions[i]
            min_distance = min(min_distance, distance)
        if min_distance <= 5:
            return 0.3
        elif min_distance <= 10:
            return 0.2
        elif min_distance <= 20:
            return 0.1
        else:
            return 0.0
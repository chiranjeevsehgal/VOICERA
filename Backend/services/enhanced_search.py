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

# Configure logging
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
        # Only initialize once
        if not self._initialized:
            logger.info("Initializing EnhancedSearch instance...")
            self.chunk_size = 100
            self.chunk_overlap = 50
            self.min_chunk_size = 30
            self.max_parallel_tasks = 10
            self.batch_size = 50
            self.context_window = 2  # Number of chunks to consider for context
            
            # Initialize Pinecone connection
            if not index:
                logger.info("Initializing Pinecone connection...")
                init_pinecone()
                if not index:
                    logger.warning("Failed to initialize Pinecone connection")
            
            self._initialized = True
            logger.info("EnhancedSearch initialization complete")

    def create_semantic_chunks(self, text: str) -> List[Dict]:
        """
        Create chunks based on semantic boundaries (sentences, paragraphs)
        with overlapping to maintain context
        """
        # Split into sentences (basic implementation)
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence_length = len(sentence.split())
            
            # If adding this sentence exceeds chunk size, create new chunk
            if current_length + sentence_length > self.chunk_size and len(current_chunk) >= self.min_chunk_size:
                # Create chunk
                chunk_text = ' '.join(current_chunk)
                chunks.append({
                    "text": chunk_text,
                    "length": current_length
                })
                
                # Start new chunk with overlap
                overlap_size = min(self.chunk_overlap, len(current_chunk))
                current_chunk = current_chunk[-overlap_size:]
                current_length = sum(len(s.split()) for s in current_chunk)
            
            current_chunk.append(sentence)
            current_length += sentence_length
        
        # Add final chunk if it meets minimum size
        if current_length >= self.min_chunk_size:
            chunks.append({
                "text": ' '.join(current_chunk),
                "length": current_length
            })
            
        return chunks

    async def hybrid_search(
        self,
        query: str,
        limit: int = 10,
        filter_dict: Optional[Dict] = None,
        original_query: Optional[str] = None
    ) -> List[Dict]:
        """
        Perform hybrid search with improved context awareness and relevance scoring
        
        Args:
            query: The search query (may be expanded/processed)
            limit: Maximum number of results to return
            filter_dict: Optional filters to apply
            original_query: The original user query for technical term scoring
        """
        try:
            # Use original query if provided, otherwise use the processed query
            query_for_tech_scoring = original_query or query
            
            # Ensure Pinecone connection
            if not index:
                logger.info("Reinitializing Pinecone connection...")
                if not init_pinecone():
                    logger.error("Could not initialize Pinecone connection")
                    return []

            # Log search parameters
            logger.info(f"Performing hybrid search with query: {query}, original query: {query_for_tech_scoring}")
            if filter_dict:
                logger.info(f"Using filters: {filter_dict}")

            # 1. Generate query embedding and extract key terms
            query_embedding = get_embedding(query)
            query_terms = self._extract_key_terms(query)
            
            # 2. Perform semantic search with larger initial pool
            semantic_limit = min(limit * 5, 150)  # Increased pool for better filtering
            semantic_results = await self._semantic_search(
                query_embedding=query_embedding,
                limit=semantic_limit,
                filter_dict=filter_dict
            )
            
            # Add original query to results for technical scoring
            for result in semantic_results:
                result["original_query"] = query_for_tech_scoring
            
            # Debug logging
            logger.info(f"Found {len(semantic_results)} semantic results")
            
            if not semantic_results:
                logger.warning("No semantic results found, check Pinecone connection and index content")
                return []

            # 3. Enhanced keyword matching with context
            keyword_results = await self._context_aware_keyword_search(
                query=query,
                query_terms=query_terms,
                texts=[r["text"] for r in semantic_results],
                metadata=[{
                    "file_name": r.get("file_name"),
                    "start_time": r.get("start_time"),
                    "end_time": r.get("end_time")
                } for r in semantic_results]
            )
            
            # 4. Combine results with context-aware scoring
            combined_results = await self._combine_results_with_context(
                semantic_results=semantic_results,
                keyword_scores=keyword_results,
                weights={
                    "semantic": 0.6,
                    "keyword": 0.4
                }
            )
            
            # 5. Apply improved diversity filtering
            try:
                diverse_results = await self._apply_context_aware_diversity_filter(
                    results=combined_results,
                    similarity_threshold=0.85,
                    max_results=limit
                )
            except Exception as e:
                logger.error(f"Error in diversity filtering: {str(e)}")
                logger.info("Falling back to combined results without diversity filtering")
                diverse_results = combined_results[:limit]
            
            return diverse_results[:limit]
            
        except Exception as e:
            logger.error(f"Error in hybrid search: {str(e)}")
            return []

    def _extract_key_terms(self, query: str) -> Dict[str, float]:
        """
        Extract and weight key terms from query
        """
        # Remove common words and punctuation
        cleaned_query = re.sub(r'[^\w\s]', ' ', query.lower())
        words = cleaned_query.split()
        
        # Weight terms by importance
        term_weights = {}
        for word in words:
            if len(word) > 2 and word not in self._get_stopwords():
                # Higher weight for repeated terms
                term_weights[word] = term_weights.get(word, 0) + 1.0
                
                # Boost weight for likely important terms
                if word in ['why', 'how', 'what', 'when', 'where', 'who']:
                    term_weights[word] *= 1.2
                elif word.endswith(('ing', 'ed', 'ion', 'ment')):  # Action/concept terms
                    term_weights[word] *= 1.3
                elif word in ['not', 'never', 'no']:  # Negation terms
                    term_weights[word] *= 1.5
        
        return term_weights

    async def _context_aware_keyword_search(
        self,
        query: str,
        query_terms: Dict[str, float],
        texts: List[str],
        metadata: List[Dict]
    ) -> List[float]:
        """
        Perform keyword search with context awareness and return scores aligned
        to the original semantic_results/texts order.
        """
        # Prepare aligned scores
        aligned_scores = [0.0] * len(texts)

        # Build sortable entries preserving original indices
        entries = [
            (i, (texts[i] or ""), metadata[i] if i < len(metadata) else {})
            for i in range(len(texts))
        ]

        # Sort by file name and start time to establish contextual order within each file
        entries.sort(key=lambda x: (x[2].get('file_name'), x[2].get('start_time', 0)))

        # Iterate per file to compute context-aware scores
        current_file = None
        group: List[tuple] = []

        def flush_group(g: List[tuple]):
            # Compute scores within this group using local positional context
            for idx_in_group, (orig_idx, text, meta) in enumerate(g):
                text_lower = (text or "").lower()
                # Basic term matching score
                term_score = 0.0
                for term, weight in query_terms.items():
                    if term in text_lower:
                        term_score += weight

                # Context bonus from neighboring chunks in same file
                context_bonus = 0.0
                start_idx = max(0, idx_in_group - self.context_window)
                end_idx = min(len(g), idx_in_group + self.context_window + 1)
                for j in range(start_idx, end_idx):
                    if j == idx_in_group:
                        continue
                    neighbor_text_lower = (g[j][1] or "").lower()
                    distance_factor = 1 / (abs(j - idx_in_group) + 1)
                    for term, weight in query_terms.items():
                        if term in neighbor_text_lower:
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
                # Flush previous file group and start a new one
                flush_group(group)
                current_file = file_name
                group = [entry]

        # Flush the last group
        if group:
            flush_group(group)

        return aligned_scores

    def _group_by_context(self, texts: List[str], metadata: List[Dict]) -> List[List[str]]:
        """
        Group texts by file and temporal proximity
        """
        # Sort by file name and start time
        sorted_pairs = sorted(
            zip(texts, metadata),
            key=lambda x: (x[1]['file_name'], x[1].get('start_time', 0))
        )
        
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

    def _calculate_context_bonus(
        self,
        text: str,
        group: List[str],
        query_terms: Dict[str, float]
    ) -> float:
        """
        Calculate context bonus based on term presence in nearby chunks
        """
        text_idx = group.index(text)
        context_bonus = 0
        
        # Check surrounding chunks within context window
        start_idx = max(0, text_idx - self.context_window)
        end_idx = min(len(group), text_idx + self.context_window + 1)
        
        for i in range(start_idx, end_idx):
            if i != text_idx:
                context_text = group[i].lower()
                # Diminishing bonus based on distance
                distance_factor = 1 / (abs(i - text_idx) + 1)
                
                for term, weight in query_terms.items():
                    if term in context_text:
                        context_bonus += weight * distance_factor * 0.5
        
        return context_bonus

    def _get_stopwords(self) -> set:
        """Get enhanced stopwords list"""
        return frozenset({
            "a", "an", "and", "are", "as", "at", "be", "by", "for",
            "from", "has", "he", "in", "is", "it", "its", "of", "on",
            "that", "the", "to", "was", "were", "will", "with",
            # Conversational fillers and generic words
            "said", "say", "says", "she", "he", "they", "we", "you",
            "yeah", "okay", "ok", "um", "uh", "like", "well", "right",
            "oh", "hi", "hello", "thanks", "thank", "please", "just"
        })

    async def _semantic_search(
        self,
        query_embedding: List[float],
        limit: int,
        filter_dict: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Perform semantic search using Pinecone with improved error handling
        """
        try:
            if not index:
                from services.pinecone_service import init_pinecone
                if not init_pinecone():
                    print("Error: Could not initialize Pinecone")
                    return []
            
            results = index.query(
                vector=query_embedding,
                top_k=limit,
                include_metadata=True,
                filter=filter_dict
            )
            
            if not results or not results.get("matches"):
                print(f"No results found for query (limit: {limit})")
                return []
                
            return [{
                **match["metadata"],
                "semantic_score": match["score"],
                "text": match["metadata"].get("text", "")
            } for match in results["matches"]]
            
        except Exception as e:
            print(f"Error in semantic search: {str(e)}")
            return []

    async def _batched_keyword_search(
        self,
        query: str,
        texts: List[str]
    ) -> List[float]:
        """
        Perform keyword-based search using batched processing
        """
        query_terms = set(self._normalize_text(query))
        scores = []
        
        # Process texts in batches
        batch_size = self.batch_size
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            # Process batch in parallel
            with ThreadPoolExecutor(max_workers=self.max_parallel_tasks) as executor:
                batch_scores = list(executor.map(
                    partial(self._calculate_keyword_score, query_terms=query_terms),
                    batch
                ))
            scores.extend(batch_scores)
        
        return scores

    def _calculate_keyword_score(self, text: str, query_terms: set) -> float:
        """
        Calculate keyword score for a single text
        """
        text_terms = set(self._normalize_text(text))
        
        # Calculate Jaccard similarity
        intersection = len(query_terms & text_terms)
        union = len(query_terms | text_terms)
        
        # Calculate term frequency score
        term_freq_score = sum(text.lower().count(term.lower()) for term in query_terms) / len(text.split())
        
        # Combine scores
        return (intersection / union if union > 0 else 0) + term_freq_score

    async def _combine_results_batched(
        self,
        semantic_results: List[Dict],
        keyword_scores: List[float],
        weights: Dict[str, float]
    ) -> List[Dict]:
        """
        Combine semantic and keyword search results with batched processing
        """
        combined_results = []
        
        # Normalize scores in batches
        max_semantic = max(r["semantic_score"] for r in semantic_results) if semantic_results else 1
        max_keyword = max(keyword_scores) if keyword_scores else 1
        
        batch_size = self.batch_size
        for i in range(0, len(semantic_results), batch_size):
            batch_semantic = semantic_results[i:i + batch_size]
            batch_keyword = keyword_scores[i:i + batch_size]
            
            # Process batch
            batch_combined = []
            for result, keyword_score in zip(batch_semantic, batch_keyword):
                normalized_semantic = result["semantic_score"] / max_semantic
                normalized_keyword = keyword_score / max_keyword
                
                combined_score = (
                    weights["semantic"] * normalized_semantic +
                    weights["keyword"] * normalized_keyword
                )
                
                batch_combined.append({
                    **result,
                    "combined_score": combined_score,
                    "keyword_score": keyword_score
                })
            
            combined_results.extend(batch_combined)
        
        # Sort by combined score
        combined_results.sort(key=lambda x: x["combined_score"], reverse=True)
        return combined_results

    async def _apply_context_aware_diversity_filter(
        self,
        results: List[Dict],
        similarity_threshold: float = 0.85,
        max_results: int = 10
    ) -> List[Dict]:
        """
        Apply diversity filtering with context awareness
        """
        if not results:
            return []
            
        diverse_results = [results[0]]  # Always keep the highest scoring result
        candidates = results[1:]
        
        while len(diverse_results) < max_results and candidates:
            most_diverse_candidate = None
            max_min_distance = -1
            
            for candidate in candidates:
                # Calculate minimum distance to all selected results
                min_distance = float('inf')
                for selected in diverse_results:
                    # Calculate semantic distance
                    similarity = self._calculate_text_similarity(
                        candidate.get("text", ""),
                        selected.get("text", "")
                    )
                    distance = 1 - similarity
                    min_distance = min(min_distance, distance)
                
                # Keep track of the candidate with the largest minimum distance
                if min_distance > max_min_distance:
                    max_min_distance = min_distance
                    most_diverse_candidate = candidate
            
            # If we found a sufficiently diverse candidate, add it
            if most_diverse_candidate and max_min_distance > (1 - similarity_threshold):
                diverse_results.append(most_diverse_candidate)
                candidates.remove(most_diverse_candidate)
            else:
                # If no sufficiently diverse candidates found, break
                break
        
        return diverse_results

    def _calculate_text_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate semantic similarity between two texts
        """
        if not text1 or not text2:
            return 0.0
            
        # Normalize texts
        words1 = set(self._normalize_text(text1))
        words2 = set(self._normalize_text(text2))
        
        # Calculate Jaccard similarity
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        return intersection / union if union > 0 else 0.0

    def _normalize_text(self, text: str) -> List[str]:
        """
        Normalize text for comparison
        """
        # Convert to lowercase and split
        words = text.lower().split()
        
        # Remove stopwords and short words
        return [w for w in words if w not in self._get_stopwords() and len(w) > 2]

    async def _combine_results_with_context(
        self,
        semantic_results: List[Dict],
        keyword_scores: List[float],
        weights: Dict[str, float]
    ) -> List[Dict]:
        """
        Combine semantic and keyword results with context awareness and technical term scoring
        """
        try:
            if not semantic_results:
                print("Warning: No semantic results found")
                return []

            if not keyword_scores:
                print("Warning: No keyword scores found")
                return semantic_results

            # Initialize technical scorer
            tech_scorer = TechnicalTermsScorer()

            # Normalize scores
            max_semantic = max(r.get("semantic_score", 0) for r in semantic_results)
            max_keyword = max(keyword_scores) if keyword_scores else 1

            # Determine dynamic weighting based on query specificity (short queries rely more on keywords)
            # We infer the query from the first result's original_query (present on all)
            original_query = semantic_results[0].get("original_query", "") if semantic_results else ""
            cleaned_query = re.sub(r'[^\w\s]', ' ', original_query.lower()).strip()
            query_terms = [w for w in cleaned_query.split() if w and w not in self._get_stopwords()]
            # Heuristic: if query is short (<=2 terms) or contains a rare/long token, boost keyword weight
            short_query = len(query_terms) <= 2
            has_specific_token = any(len(t) >= 7 for t in query_terms)

            if short_query or has_specific_token:
                dyn_weights = {"semantic": 0.3, "keyword": 0.5, "technical": 0.2}
            else:
                dyn_weights = {"semantic": 0.4, "keyword": 0.3, "technical": 0.3}

            combined_results = []
            for result, keyword_score in zip(semantic_results, keyword_scores):
                # Ensure all required fields are present
                if "text" not in result:
                    print(f"Warning: Missing text field in result: {result}")
                    continue

                normalized_semantic = result.get("semantic_score", 0) / max_semantic if max_semantic else 0
                normalized_keyword = keyword_score / max_keyword if max_keyword else 0

                # Calculate technical relevance score
                raw_tech_score = tech_scorer.calculate_technical_score(
                    text=result.get("text", ""),
                    query=result.get("original_query", "")
                )
                # Map technical score to 0..1 range. Treat <=0 as 0, cap at 1.
                # If the scorer returns in [0,1], this is a no-op; if it returns up to 2, we compress.
                # Map such that 1.0 (neutral) -> 0.0, 2.0 (max) -> 1.0
                tech_score = max(0.0, min(1.0, raw_tech_score - 1.0))

                # Base combination with dynamic weights
                combined_score = (
                    dyn_weights["semantic"] * normalized_semantic +
                    dyn_weights["keyword"] * normalized_keyword +
                    dyn_weights["technical"] * tech_score
                )

                # Strong penalty if there's zero keyword match for specific/short queries
                if (short_query or has_specific_token) and normalized_keyword == 0:
                    # down-rank items that share no lexical overlap with the query
                    combined_score *= 0.2

                # Hard relevance gate: for short/specific queries, discard items with
                # - no keyword evidence
                # - no technical overlap (tech_score ~ 0)
                # - very low semantic score (both normalized and absolute thresholds)
                # - and the query term(s) not present in the text
                if (short_query or has_specific_token):
                    raw_semantic = result.get("semantic_score", 0.0)
                    text_lower = result.get("text", "").lower()
                    has_query_token_in_text = any(t in text_lower for t in query_terms)
                    if normalized_keyword == 0 and tech_score <= 0.01 and (normalized_semantic < 0.2 or raw_semantic < 0.2) and not has_query_token_in_text:
                        # Skip this result entirely as likely irrelevant
                        continue

                # Add all metadata fields
                combined_result = {
                    **result,
                    "combined_score": combined_score,
                    "keyword_score": normalized_keyword,
                    "semantic_score": normalized_semantic,
                    "technical_score": tech_score,
                    "weights_used": {
                        "semantic": dyn_weights["semantic"],
                        "keyword": dyn_weights["keyword"],
                        "technical": dyn_weights["technical"]
                    }
                }

                combined_results.append(combined_result)

            # Sort by combined score
            combined_results.sort(key=lambda x: x["combined_score"], reverse=True)

            # Debug logging
            print(f"Combined {len(combined_results)} results")
            if combined_results:
                print(f"Top score: {combined_results[0]['combined_score']}")
                print(f"Technical score: {combined_results[0]['technical_score']}")
            
            return combined_results
            
        except Exception as e:
            print(f"Error combining results: {str(e)}")
            # Return semantic results as fallback
            return semantic_results

class TechnicalTermsScorer:
    def __init__(self):
        # Common words that usually don't indicate technical/domain-specific content
        self.common_words = {
            'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from', 'has', 'he', 
            'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the', 'to', 'was', 'were', 
            'will', 'with', 'about', 'above', 'after', 'again', 'all', 'also', 'am', 
            'any', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'can', 
            'did', 'do', 'does', 'doing', 'down', 'during', 'each', 'few', 'further', 
            'had', 'have', 'having', 'her', 'here', 'hers', 'herself', 'him', 'himself', 
            'his', 'how', 'i', 'if', 'into', 'just', 'me', 'more', 'most', 'my', 'myself',
            'no', 'nor', 'not', 'now', 'or', 'other', 'our', 'ours', 'ourselves', 'out',
            'over', 'own', 'same', 'she', 'should', 'so', 'some', 'such', 'than', 'then',
            'there', 'these', 'they', 'this', 'those', 'through', 'too', 'under', 'until',
            'up', 'very', 'we', 'what', 'when', 'where', 'which', 'while', 'who', 'whom',
            'why', 'you', 'your', 'yours', 'yourself', 'yourselves'
        }

    def _extract_significant_terms(self, text: str) -> set:
        """
        Extract potentially significant terms from text by:
        1. Removing common words
        2. Identifying multi-word phrases
        3. Finding specialized/longer terms
        """
        # Normalize text
        text_lower = text.lower()
        
        # Split into words
        words = text_lower.split()
        
        # Extract single words (excluding common words and short terms)
        significant_terms = {
            word for word in words 
            if word not in self.common_words 
            and len(word) > 3  # Filter out very short words
        }
        
        # Extract potential multi-word phrases (2-3 words)
        for i in range(len(words) - 1):
            # Two-word phrases
            phrase = f"{words[i]} {words[i+1]}"
            if not any(word in self.common_words for word in phrase.split()):
                significant_terms.add(phrase)
            
            # Three-word phrases
            if i < len(words) - 2:
                phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
                if not any(word in self.common_words for word in phrase.split()):
                    significant_terms.add(phrase)
        
        return significant_terms

    def calculate_technical_score(self, text: str, query: str) -> float:
        """
        Calculate relevance score based on shared significant terms between query and text
        """
        if not text or not query:
            return 0.0
            
        # Extract significant terms
        query_terms = self._extract_significant_terms(query)
        text_terms = self._extract_significant_terms(text)
        
        if not query_terms or not text_terms:
            return 1.0  # Neutral score if no significant terms found
        
        # Calculate term overlap
        matching_terms = query_terms & text_terms
        
        if not matching_terms:
            return 1.0  # Neutral score if no matching terms
            
        # Calculate base score based on term overlap ratio
        overlap_ratio = len(matching_terms) / len(query_terms)
        base_score = 1.0 + (overlap_ratio * 0.5)  # Max 50% boost from overlap
        
        # Additional scoring factors:
        
        # 1. Boost for longer matching terms (likely more specific/technical)
        long_term_bonus = sum(0.1 for term in matching_terms if len(term.split()) > 1)
        
        # 2. Proximity bonus for matching terms that appear close together
        proximity_bonus = self._calculate_proximity_bonus(text, matching_terms)
        
        # 3. Density bonus for segments with high concentration of matching terms
        density_bonus = len(matching_terms) / len(text.split()) * 0.3
        
        final_score = base_score + long_term_bonus + proximity_bonus + density_bonus
        
        return min(final_score, 2.0)  # Cap maximum score at 2.0

    def _calculate_proximity_bonus(self, text: str, matching_terms: set) -> float:
        """
        Calculate bonus score based on how close matching terms appear to each other
        """
        if len(matching_terms) < 2:
            return 0.0
            
        words = text.lower().split()
        term_positions = []
        
        # Find positions of all matching terms
        for i, word in enumerate(words):
            for term in matching_terms:
                if term.startswith(word):
                    # Check if multi-word term matches at this position
                    term_words = term.split()
                    if i + len(term_words) <= len(words):
                        if ' '.join(words[i:i+len(term_words)]) == term:
                            term_positions.append(i)
        
        if not term_positions or len(term_positions) < 2:
            return 0.0
            
        # Calculate minimum distance between any two matching terms
        min_distance = float('inf')
        for i in range(len(term_positions) - 1):
            distance = term_positions[i + 1] - term_positions[i]
            min_distance = min(min_distance, distance)
        
        # Convert distance to bonus score (closer terms = higher bonus)
        if min_distance <= 5:  # Terms very close
            return 0.3
        elif min_distance <= 10:  # Terms moderately close
            return 0.2
        elif min_distance <= 20:  # Terms somewhat close
            return 0.1
        else:
            return 0.0  # Terms too far apart
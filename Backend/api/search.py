from fastapi import APIRouter, Query, HTTPException, Depends
from typing import Optional, List, Dict, Tuple
from services.pinecone_service import search_transcripts, test_pinecone_connection
from services.enhanced_search import EnhancedSearch, TechnicalTermsScorer
from services.auth import get_current_user
from services.transcript_service import extract_transcript
from pydantic import BaseModel, Field
import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
import re
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from services.database import podcasts_collection, uploads_collection
from utils.analytics import track_search_term, track_user_activity
from utils.logging import log_error, log_info, log_warning

router = APIRouter()

# Initialize EnhancedSearch
enhanced_search = EnhancedSearch()

# Initialize logger
logger = logging.getLogger(__name__)

# Configure max workers for parallel processing
MAX_PARALLEL_VALIDATIONS = 5  # Adjust based on your API rate limits and system capacity

class LLMConfig_Search:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.model_name = os.getenv("GEMINI_MODEL")
        self.temperature = 0.0  # 0 for deterministic expansion
        self.max_tokens = None
        self.top_p = 1.0
        self.top_k = 1
        
        # System prompt for query expansion
        self.system_prompt = """You are a query expansion assistant. Your task is to expand search queries 
        to include alternative formats of numbers and words. For example, if the query contains "21", 
        include "twenty one" and "twenty-one". If it contains "twenty one", include "21". 
        Don't change the meaning of the query - just expand it to include alternative formats.
        Return a JSON object with the original query and expanded variations like:
        {"original": "original query", "expanded": ["variation1", "variation2"]}"""
        
        # System prompt for natural language query processing
        self.nl_query_prompt = """You are a natural language query processor for an audio search system.
        Your task is to analyze natural language queries and extract the following in JSON format:
        1. key_terms: Important words or phrases to search for (list of strings)
        2. entities: Named entities like people, places, or dates (list of strings)
        3. temporal_references: Any time references like days, dates, or times (list of strings)
        4. search_intent: The primary information the user is looking for (string)
        5. search_query: A reformulated search query optimized for semantic search (string)
        
        For example, if the query is "which audio file talks about the marketing meeting on Thursday?", return:
        {
          "key_terms": ["marketing meeting", "meeting", "Thursday"],
          "entities": ["marketing"],
          "temporal_references": ["Thursday"],
          "search_intent": "Find audio files discussing a marketing meeting scheduled on Thursday",
          "search_query": "marketing meeting Thursday"
        }
        
        Return the JSON object only, with no additional text."""
        
        # System prompt for final reranking
        self.reranking_prompt = """You are an expert search result evaluator for an audio search system.
        Your task is to analyze and rerank search results based on their relevance to the user's query.
        
        Consider the following aspects when evaluating each result:
        1. Direct relevance to the query intent and key terms
        2. Contextual understanding and semantic matching
        3. Information completeness and quality
        4. Temporal and logical coherence
        5. Presence of key entities and concepts
        
        For each result, assign a score from 0 to 1 where:
        - 1.0: Perfect match, contains exactly what the user is looking for
        - 0.8-0.9: Very relevant, covers most aspects of the query
        - 0.6-0.7: Moderately relevant, covers some important aspects
        - 0.4-0.5: Somewhat relevant, touches on the topic
        - 0.0-0.3: Not very relevant or off-topic
        
        Return a JSON array of objects, each containing:
        {
          "result_id": "unique_id_of_result",
          "llm_score": float_score,
          "explanation": "Brief explanation of the score"
        }
        
        Original Query: {query}
        Search Intent: {search_intent}
        
        Results to evaluate:
        {results_json}
        
        Evaluate each result and return the JSON array only, no additional text."""
        
        # System prompt for generating answers from transcripts
        self.answer_generation_prompt = """You are an AI assistant analyzing audio transcripts.
        Your task is to answer a user's question based ONLY on the provided transcript content.
        
        Guidelines:
        1. Only answer based on information found in the transcript.
        2. If the transcript doesn't contain the information needed to answer the question, clearly state:
           "The transcript does not contain information about [specific topic from the question]."
        3. Be concise but thorough in your answers.
        4. Include relevant quotes or timestamps if available in the transcript.
        5. DO NOT make up or infer information that is not explicitly stated in the transcript.
        6. DO NOT use your general knowledge - rely EXCLUSIVELY on the provided transcript.
        
        Here is the full transcript content:
        -----------------------------
        {transcript}
        -----------------------------
        
        User question: {query}
        
        Your answer should directly respond to the question using ONLY information from the transcript.
        If the answer cannot be found in the transcript, clearly state that the information is not available."""
        
        # Initialize LLM if API key is available
        if self.api_key:
            genai.configure(api_key=self.api_key)

async def expand_query_with_llm(query: str) -> List[str]:
    """
    Use LLM to expand query with alternative formats (e.g., numbers as words)
    """
    config = LLMConfig_Search()
    
    if not config.api_key:
        # If no API key, just return the original query
        return [query]
    
    try:
        # Configuring the model
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": config.temperature,
                "max_output_tokens": config.max_tokens,
                "top_p": config.top_p,
                "top_k": config.top_k
            }
        )
        
        # Construct prompt to expand the query
        prompt = f"Expand this search query to include variations of numbers and words: {query}"
        
        response = model.generate_content(
            [config.system_prompt, prompt]
        )
        
        try:
            # Parse the response as JSON
            result = json.loads(response.text)
            
            # Return the expanded queries
            expanded_queries = result.get("expanded", [])
            if not expanded_queries or not isinstance(expanded_queries, list):
                return [query]  # Fallback to original if no proper expansions
                
            # Add the original query if not already in the list
            if query not in expanded_queries:
                expanded_queries.insert(0, query)
                
            return expanded_queries
            
        except json.JSONDecodeError:
            # If not JSON, just return the original query
            return [query]
            
    except Exception as e:
        log_error(f"Error in query expansion: {str(e)}", "search.expand_query_with_llm", {"query": query, "error": str(e)})
        return [query]  # Fallback to original query

async def process_natural_language_query(query: str) -> Dict:
    """
    Process natural language queries to extract relevant search terms and context
    """
    config = LLMConfig_Search()
    
    # Common English stopwords to filter out
    stopwords = {
        "a", "about", "above", "across", "after", "again", "against", "all", "almost", "alone", 
    "along", "already", "also", "although", "always", "am", "among", "amongst", "an", "and", 
    "announce", "another", "any", "anybody", "anyhow", "anymore", "anyone", "anything", "anyway", 
    "anyways", "anywhere", "apparently", "approximately", "are", "aren", "arent", "aren't", 
    "arise", "around", "as", "aside", "ask", "asking", "at", "auth", "available", "away", 
    "awfully", "b", "back", "be", "became", "because", "become", "becomes", "becoming", 
    "been", "before", "beforehand", "begin", "beginning", "beginnings", "begins", "behind", 
    "being", "believe", "below", "beside", "besides", "between", "beyond", "biol", "both", 
    "brief", "briefly", "but", "by", "c", "ca", "came", "can", "cannot", "can't", "cause", 
    "causes", "certain", "certainly", "co", "com", "come", "comes", "contain", "containing", 
    "contains", "could", "couldnt", "couldn't", "d", "date", "did", "didn't", "different", 
    "do", "does", "doesn't", "doing", "don", "don't", "done", "down", "downwards", "due", 
    "during", "e", "each", "ed", "edu", "effect", "eg", "eight", "eighty", "either", "else", 
    "elsewhere", "end", "ending", "enough", "especially", "et", "et-al", "etc", "even", 
    "ever", "every", "everybody", "everyone", "everything", "everywhere", "ex", "except", 
    "f", "far", "few", "ff", "fifth", "first", "five", "fix", "followed", "following", 
    "follows", "for", "former", "formerly", "forth", "found", "four", "from", "further", 
    "furthermore", "g", "gave", "get", "gets", "getting", "give", "given", "gives", "giving", 
    "go", "goes", "gone", "got", "gotten", "h", "had", "hadn't", "has", "hasn't", "have", 
    "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", 
    "herself", "him", "himself", "his", "how", "how's", "however", "hundred", "i", "i'd", 
    "i'll", "i'm", "i've", "ie", "if", "in", "inc", "indeed", "index", "information", 
    "instead", "into", "invention", "is", "isn't", "it", "it's", "its", "itself", "j", 
    "just", "k", "keep", "keeps", "kept", "kg", "km", "know", "known", "knows", "l", 
    "largely", "last", "lately", "later", "latter", "latterly", "least", "less", "lest", 
    "let", "let's", "lets", "like", "liked", "likely", "line", "little", "look", "looking", 
    "looks", "ltd", "m", "made", "mainly", "make", "makes", "many", "may", "maybe", 
    "me", "mean", "means", "meantime", "meanwhile", "merely", "mg", "might", "million", 
    "miss", "ml", "more", "moreover", "most", "mostly", "mr", "mrs", "much", "mug", 
    "must", "my", "myself", "n", "na", "name", "namely", "nay", "nd", "near", "nearly", 
    "necessarily", "necessary", "need", "needs", "neither", "never", "nevertheless", 
    "new", "next", "nine", "ninety", "no", "nobody", "non", "none", "nonetheless", 
    "noone", "nor", "normally", "nos", "not", "noted", "nothing", "now", "nowhere", 
    "o", "obtain", "obtained", "obviously", "of", "off", "often", "oh", "ok", "okay", 
    "old", "omitted", "on", "once", "one", "ones", "only", "onto", "or", "ord", "other", 
    "others", "otherwise", "ought", "our", "ours", "ourselves", "out", "outside", "over", 
    "overall", "owing", "own", "p", "page", "pages", "part", "particular", "particularly", 
    "past", "per", "perhaps", "placed", "please", "plus", "poorly", "possible", "possibly", 
    "potentially", "pp", "predominantly", "present", "previously", "primarily", "probably", 
    "promptly", "proud", "provides", "put", "q", "que", "quickly", "quite", "qv", "r", 
    "ran", "rather", "rd", "re", "readily", "really", "recent", "recently", "ref", "refs", 
    "regarding", "regardless", "regards", "related", "relatively", "research", "respectively", 
    "resulted", "resulting", "results", "right", "run", "s", "said", "same", "saw", "say", 
    "saying", "says", "sec", "section", "see", "seeing", "seem", "seemed", "seeming", 
    "seems", "seen", "self", "selves", "sent", "seven", "several", "shall", "shan't", 
    "she", "she'd", "she'll", "she's", "should", "shouldn't", "show", "showed", "shown", 
    "shows", "significant", "significantly", "similar", "similarly", "since", "six", 
    "slightly", "so", "some", "somebody", "somehow", "someone", "somethan", "something", 
    "sometime", "sometimes", "somewhat", "somewhere", "soon", "sorry", "specifically", 
    "specified", "specify", "specifying", "still", "stop", "strongly", "sub", "substantially", 
    "successfully", "such", "sufficiently", "suggest", "sup", "sure", "t", "take", "taken", 
    "taking", "tell", "tends", "th", "than", "thank", "thanks", "thanx", "that", "that's", 
    "that'll", "thats", "that've", "the", "their", "theirs", "them", "themselves", "then", 
    "thence", "there", "thereafter", "thereby", "thered", "therefore", "therein", "there'll", 
    "thereof", "therere", "theres", "thereto", "thereupon", "there've", "these", "they", 
    "they'd", "they'll", "they're", "they've", "think", "this", "those", "though", "thousand", 
    "three", "throug", "through", "throughout", "thru", "thus", "til", "till", "tip", 
    "to", "together", "too", "took", "toward", "towards", "tried", "tries", "truly", 
    "try", "trying", "ts", "twice", "two", "u", "un", "under", "unfortunately", "unless", 
    "unlike", "unlikely", "until", "unto", "up", "upon", "ups", "us", "use", "used", 
    "useful", "usefully", "usefulness", "uses", "using", "usually", "v", "value", "various", 
    "very", "via", "viz", "vol", "vols", "vs", "w", "want", "wants", "was", "wasn't", 
    "way", "we", "we'd", "we'll", "we're", "we've", "welcome", "went", "were", "weren't", 
    "what", "what's", "what'll", "whatve", "when", "when's", "whence", "whenever", "where", 
    "where's", "whereafter", "whereas", "whereby", "wherein", "whereupon", "wherever", 
    "whether", "which", "while", "whim", "whither", "who", "who's", "who'd", "whoever", 
    "whole", "whom", "whomever", "whose", "why", "why's", "widely", "will", "willing", 
    "wish", "with", "within", "without", "won't", "words", "world", "would", "wouldn't", 
    "www", "x", "y", "yes", "yet", "you", "you'd", "you'll", "you're", "you've", "your", 
    "yours", "yourself", "yourselves", "z", "zero", "'tis", "'twas", "10", "39", "a's", 
    "able", "abst", "accordance", "according", "accordingly", "act", "actually", "added", 
    "adj", "affected", "affecting", "affects", "afterwards", "ah", "ai", "ain't", "aint", 
    "al", "allow", "allows", "alongside", "amid", "amidst", "amoungst", "amount", "ao", 
    "apart", "appear", "appreciate", "appropriate", "aq", "ar", "area", "areas", "arpa", 
    "asked", "asks", "associated", "au", "aw聆听aw", "az", "ba", "backed", "backing", 
    "backs", "backward", "backwards", "bb", "bd", "began", "beings", "best", "better", 
    "bf", "bg", "bh", "bi", "big", "bill", "billion", "bj", "bm", "bn", "bo", "bottom", 
    "br", "bs", "bt", "buy", "bv", "bw", "bz", "c'mon", "c's", "call", "cant", "caption", 
    "case", "cases", "cc", "cd", "cf", "cg", "ch", "changes", "ci", "ck", "cl", "clear", 
    "clearly", "click", "cm", "cmon", "cn", "co.", "computer", "con", "concerning", 
    "consequently", "consider", "considering", "copy", "corresponding", "could've", 
    "couldn", "course", "cr", "cry", "cs", "cu", "currently", "cv", "cx", "cy", "cz", 
    "dare", "daren't", "darent", "de", "dear", "definitely", "describe", "described", 
    "despite", "detail", "didn", "differ", "differently", "directly", "dj", "dk", "dm", 
    "doesn", "doner", "dones", "donest", "dont", "dos", "dost", "doubtful", "downed", 
    "downing", "downs", "dz", "early", "ec", "ee", "eh", "eleven", "empty", "ended", 
    "ends", "entirely", "er", "es", "evenly", "evermore", "exactly", "example", "face", 
    "faces", "fact", "facts", "fairly", "farther", "felt", "fewer", "fi", "fifteen", 
    "fifty", "fify", "fill", "find", "finds", "fire", "fj", "fk", "fm", "fo", "forever", 
    "forty", "forward", "fr", "free", "front", "full", "fully", "furthered", "furthering", 
    "furthers", "fx", "ga", "gb", "gd", "ge", "general", "generally", "gf", "gg", "gh", 
    "gi", "gl", "gm", "gmt", "gn", "going", "good", "goods", "gov", "gp", "gq", "gr", 
    "great", "greater", "greatest", "greetings", "group", "grouped", "grouping", "groups", 
    "gs", "gt", "gu", "gw", "gy", "hadst", "half", "hasn", "hast", "hath", "haven", 
    "hell", "hello", "help", "herse", "herse”", "high", "higher", "highest", "himse", 
    "himse”", "hk", "hm", "hn", "homepage", "hopefully", "how'd", "how'll", "hr", "ht", 
    "htm", "html", "http", "hu", "i.e.", "ignored", "ii", "il", "ill", "inasmuch", "inc.", 
    "indicate", "indicated", "indicates", "inner", "inside", "insofar", "int", "interest", 
    "interested", "interesting", "interests", "io", "iq", "ir", "isn", "it'd", "itll", 
    "itse”", "ive", "je", "jm", "jo", "join", "jp", "ke", "keys", "kh", "ki", "kind", 
    "kn", "knew", "kp", "kr", "kw", "ky", "kz", "la", "large", "latest", "lb", "lc", 
    "length", "li", "likewise", "lk", "ll", "long", "longer", "longest", "low", "lower", 
    "lr", "ls", "lt", "lu", "lv", "ly", "ma", "making", "man", "mayn't", "maynt", "mc", 
    "md", "member", "members", "men", "mh", "microsoft", "might've", "mightn", "mightnt", 
    "mil", "mill", "mine", "minus", "mk", "mm", "mn", "mo", "move", "mp", "mq", "ms", 
    "msie", "mt", "mu", "must've", "mustn", "mustnt", "mv", "mw", "mx", "myse”", "mz", 
    "nc", "ne", "needed", "needing", "needn't", "neednt", "net", "netscape", "neverf", 
    "neverless", "newer", "newest", "nf", "ng", "ni", "nl", "no-one", "notwithstanding", 
    "novel", "np", "nr", "nu", "null", "number", "numbers", "nz", "older", "oldest", 
    "om", "one's", "open", "opened", "opening", "opens", "opposite", "order", "ordered", 
    "ordering", "orders", "org", "oughtn't", "oughtnt", "pa", "parted", "parting", "parts", 
    "pe", "pf", "pg", "ph", "pk", "pl", "place", "places", "pm", "pmid", "pn", "point", 
    "pointed", "pointing", "points", "pr", "presented", "presenting", "presents", 
    "presumably", "problem", "problems", "provided", "pt", "puts", "pw", "py", "qa", 
    "reasonably", "reserved", "ring", "ro", "room", "rooms", "round", "ru", "rw", "sa", 
    "sb", "sc", "sd", "se", "second", "secondly", "seconds", "sees", "sensible", "serious", 
    "seriously", "seventy", "sg", "sh", "shant", "shell", "should've", "shouldn", "shouldnt", 
    "showing", "si", "side", "sides", "sincere", "site", "sixty", "sj", "sk", "sl", "sm", 
    "small", "smaller", "smallest", "sn", "someday", "sr", "st", "state", "states", "su", 
    "sv", "sy", "system", "sz", "t's", "tc", "td", "ten", "test", "text", "tf", "tg", 
    "thatll", "thatve", "there'd", "there're", "therell", "thereve", "theyll", "theyve", 
    "thick", "thin", "thing", "things", "thinks", "third", "thirty", "thorough", "thoroughly", 
    "thought", "thoughts", "three", "till", "tis", "tj", "tk", "tm", "tn", "today", "top", 
    "tp", "tr", "trillion", "tt", "turn", "turned", "turning", "turns", "tv", "tw", "twas", 
    "twelve", "twenty", "tz", "ua", "ug", "uk", "um", "underneath", "undoing", "upwards", 
    "uucp", "uy", "uz", "va", "vc", "ve", "versus", "vg", "vi", "vn", "vu", "wanted", 
    "wanting", "wasn", "ways", "web", "webpage", "website", "well", "wells", "weren", 
    "weve", "wf", "what'd", "what've", "when'd", "when'll", "where'd", "where'll", 
    "whichever", "whilst", "who'd", "wholl", "why'd", "why'll", "width", "won", "wonder", 
    "work", "worked", "working", "works", "would've", "wouldn", "ws", "ye", "year", 
    "years", "youll", "young", "younger", "youngest", "youve", "yt", "yu", "za", "zm", 
    "zr", "I", "yond", "yonder", "yon", "zillion", "umpteen", "username", "uponed", 
    "upons", "uponing", "upping", "upped", "unliker", "unlikest", "usedest", "rath", 
    "rathest", "rathe", "relate", "res", "respecting", "qua", "neaths", "neath", "nethe", 
    "nethermost", "necessariest", "necessarier", "nigh", "nighest", "nigher", "nobodies", 
    "nowheres", "noes", "nothings", "nathless", "natheless", "tills", "tilled", "tilling", 
    "towardest", "towarder", "thy", "thyself", "thous", "thouses", "thoroughest", 
    "thorougher", "thruer", "thruest", "thro", "throughest", "througher", "thine", 
    "thises", "thee", "thenest", "thener", "therer", "therest", "owt", "owning", "owned", 
    "owns", "otherwisest", "otherwiser", "oftener", "oftenest", "offs", "offest", "oughts", 
    "ourself", "outest", "outed", "outwith", "outs", "overallest", "overaller", "overalls", 
    "overs", "orer", "orest", "oneself", "onest", "ons", "atween", "athwart", "atop", 
    "afore", "afterward", "afterest", "afterer", "ain", "anent", "anear", "andor", "ares", 
    "aest", "aer", "abaft", "abafter", "abaftest", "abovest", "abover", "abouter", 
    "aboutest", "aid", "apartest", "aparter", "appeared", "appears", "appearing", 
    "appropriating", "appropriatest", "appropriates", "appropriater", "appropriated", 
    "allest", "aller", "allyou", "alls", "albeit", "asides", "aslant", "ases", "astrider", 
    "astride", "astridest", "astraddlest", "astraddler", "astraddle", "availablest", 
    "availabler", "aughts", "aught", "variousest", "variouser", "vis-a-vis", "vis-a-viser", 
    "vis-a-visest", "veriest", "verier", "gotta", "byandby", "by-and-by", "bist", "buts", 
    "becomings", "becominger", "becomingest", "behinds", "beforehandest", "beforehander", 
    "bettered", "betters", "bettering", "betwixt", "beneath", "mucher", "muchest", 
    "musts", "musths", "musth", "main", "mayest", "mauger", "maugre", "meanwhiles", 
    "mights", "midst", "midsts", "huh", "humph", "hereafters", "hadst", "haves", "hae", 
    "hath", "hitherest", "hitherer", "how-do-you-do", "howdoyoudo", "hoos", "hoo", 
    "woulded", "woulding", "woulds", "wast", "wert", "withal", "whateverer", "whateverest", 
    "whatsoeverer", "whatsoeverest", "whatsoever", "whencesoever", "whensoever", "whenas", 
    "wheen", "whereto", "whereon", "whereof", "wherewithal", "wherewith", "whereinto", 
    "wheresoever", "wherefrom", "whichsoever", "whiles", "whithersoever", "whosoever", 
    "whoso", "syne", "syn", "shalling", "shalled", "shalls", "shoulding", "shoulded", 
    "shoulds", "sayyid", "sayid", "saider", "saidest", "samest", "sames", "samer", 
    "saved", "sans", "sanses", "sanserifs", "sanserif", "soer", "soest", "sobeit", 
    "sometimest", "sometimer", "severaler", "severalest", "seriousest", "seriouser", 
    "senza", "send", "seemingest", "seeminger", "seemings", "summat", "sups", "supping", 
    "supped", "sine", "sines", "sith", "stopped", "plaintiff", "plenty", "plenties", 
    "pleased", "pleases", "particulars", "particularest", "particularer", "pro", 
    "providing", "provide", "layabout", "layabouts", "latterest", "latterer", "latters", 
    "lots", "lotting", "lotted", "lot", "ifs", "info", "idem", "idemer", "idemest", 
    "immediatest", "immediater", "inwards", "inwardest", "inwarder", "indicating", 
    "fs", "figupon", "figupons", "figuponing", "figuponed", "fewest", "frae", "failing", 
    "failings", "furtherer", "furtherest", "fourscore", "followthrough", "forwhy", 
    "fornenst", "formerer", "formerest", "formers", "forbye", "forby", "fore", "forer", 
    "fores", "ddays", "dday", "doings", "doe", "doth", "downwarder", "downwardest", 
    "downward", "doner", "dones", "donest", "dos", "dost", "differentest", "differenter", 
    "describing", "describes", "despiting", "despites", "despited", "cum", "circa", 
    "chez", "cer", "certainest", "certainer", "cest", "canst", "cants", "canting", 
    "cantest", "canted", "couldst", "comeon", "comeons", "come-ons", "come-on", 
    "concerninger", "concerningest", "evens", "evenser", "evensest", "evened", "evenest", 
    "ere", "excepted", "excepts", "excepting", "exes",
    }
    
    if not config.api_key:
        # If no API key, return basic structure with original query
        # Filter out stopwords from the key terms
        key_terms = [term.lower() for term in query.lower().split() 
                     if term.lower() not in stopwords and len(term) > 2]
        return {
            "key_terms": key_terms,
            "entities": [],
            "temporal_references": [],
            "search_intent": f"Find information about {query}",
            "search_query": query
        }
    
    try:
        # Configuring the model
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": config.temperature,
                "max_output_tokens": config.max_tokens,
                "top_p": config.top_p,
                "top_k": config.top_k
            }
        )
        
        # Get NL query analysis
        response = model.generate_content(
            [config.nl_query_prompt, query]
        )
        
        try:
            # Parse the response as JSON
            result = json.loads(response.text)
            return result
            
        except json.JSONDecodeError:
            # Fallback to basic analysis if parsing fails
            key_terms = [term.lower() for term in query.lower().split() 
                         if term.lower() not in stopwords and len(term) > 2]
            return {
                "key_terms": key_terms,
                "entities": [],
                "temporal_references": [],
                "search_intent": f"Find information about {query}",
                "search_query": query
            }
            
    except Exception as e:
        log_error(f"Error in natural language query processing: {str(e)}", "search.process_natural_language_query", {"query": query, "error": str(e)})
        # Return basic fallback
        key_terms = [term.lower() for term in query.lower().split() 
                     if term.lower() not in stopwords and len(term) > 2]
        return {
            "key_terms": key_terms,
            "entities": [],
            "temporal_references": [],
            "search_intent": f"Find information about {query}",
            "search_query": query
        }

def parse_timestamp_range(query: str) -> tuple:
    """
    Parse timestamp ranges from queries like "policy 30-32"
    
    Args:
        query: The search query potentially containing timestamp range
        
    Returns:
        (cleaned_query, start_time, end_time) tuple
    """
    # Look for patterns like "text 30-32" or "text 1:30-2:45"
    time_range_pattern = r'(\d+:?\d*)-(\d+:?\d*)'
    match = re.search(time_range_pattern, query)
    
    if match:
        # Clean the query by removing the time range
        cleaned_query = re.sub(time_range_pattern, '', query).strip()
        
        # Parse start and end times
        start_str, end_str = match.groups()
        
        # Convert time strings to seconds
        start_time = parse_time_to_seconds(start_str)
        end_time = parse_time_to_seconds(end_str)
        
        return cleaned_query, start_time, end_time
    
    # No timestamp range found
    return query, None, None

def parse_time_to_seconds(time_str: str) -> float:
    """
    Convert time string (e.g., "30" or "1:30") to seconds
    
    Args:
        time_str: String representation of time
        
    Returns:
        Time in seconds
    """
    if ':' in time_str:
        # Format is minutes:seconds
        parts = time_str.split(':')
        if len(parts) == 2:
            minutes, seconds = parts
            return float(minutes) * 60 + float(seconds)
        elif len(parts) == 3:
            hours, minutes, seconds = parts
            return float(hours) * 3600 + float(minutes) * 60 + float(seconds)
    
    # Format is just seconds
    return float(time_str)

async def rerank_results_for_nl_query(results: List[Dict], nl_query_info: Dict) -> List[Dict]:
    """
    Rerank search results based on natural language query analysis
    
    Args:
        results: List of search results
        nl_query_info: Natural language query analysis
        
    Returns:
        Reranked list of results
    """
    if not results or not nl_query_info:
        return results
        
    # Calculate new scores based on NL query intent
    key_terms = [term.lower() for term in nl_query_info.get("key_terms", [])]
    entities = [entity.lower() for entity in nl_query_info.get("entities", [])]
    temporal_references = [ref.lower() for ref in nl_query_info.get("temporal_references", [])]
    
    all_important_terms = key_terms + entities + temporal_references
    
    # No reranking needed if we don't have important terms to match
    if not all_important_terms:
        return results
    
    for result in results:
        # Get the text and calculate a match score
        text = result.get("text", "").lower()
        
        # Base match score from semantic search
        base_score = result.get("score", 0)
        
        # Calculate bonus for each important term that appears in the text
        term_match_bonus = 0
        matched_terms = []
        
        for term in all_important_terms:
            if term in text:
                term_match_bonus += 0.1  # Add 0.1 for each term match
                matched_terms.append(term)
        
        # Calculate time reference bonus if applicable
        time_bonus = 0
        if temporal_references and any(ref in text for ref in temporal_references):
            time_bonus = 0.2  # Add 0.2 if any time reference is found
        
        # Calculate final score
        nl_score = base_score + term_match_bonus + time_bonus
        
        # Store the NL-specific scoring info
        result["nl_score"] = nl_score
        result["matched_terms"] = matched_terms
        result["has_time_match"] = time_bonus > 0
    
    # Sort by the new NL score
    results.sort(key=lambda x: -x.get("nl_score", 0))
    
    return results

async def llm_rerank_results(
    results: List[Dict],
    query: str,
    search_intent: Optional[str] = None
) -> List[Dict]:
    """
    Use LLM to perform final reranking of search results
    
    Args:
        results: List of search results to rerank
        query: Original search query
        search_intent: Optional search intent from NL processing
        
    Returns:
        Reranked list of results with LLM scoring
    """
    if not results:
        return results
        
    try:
        config = LLMConfig_Search()
        
        if not config.api_key:
            logger.warning("LLM API key not configured, skipping LLM reranking")
            return results
            
        # Prepare results for LLM evaluation
        results_for_llm = []
        for result in results:
            result_id = f"{result.get('file_name')}_{result.get('start_time')}_{result.get('end_time')}"
            results_for_llm.append({
                "result_id": result_id,
                "text": result.get("text", ""),
                "current_score": result.get("score", 0),
                "matched_terms": result.get("matched_terms", []),
                "has_exact_match": result.get("has_exact_match", False)
            })
        
        # Configure the model
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": 0.1,  # Low temperature for consistent scoring
                "max_output_tokens": 2048,
                "top_p": 0.95,
                "top_k": 40
            }
        )
        
        # Format the prompt
        formatted_prompt = config.reranking_prompt.format(
            query=query,
            search_intent=search_intent or f"Find information about: {query}",
            results_json=json.dumps(results_for_llm, indent=2)
        )
        
        # Get LLM evaluation
        response = model.generate_content(formatted_prompt)
        response_text = response.text.strip()
        
        try:
            # Clean up the response text to ensure it's valid JSON
            # Remove any markdown formatting or extra text
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
                logger.info("Extracted JSON from markdown code block")
            elif '```' in response_text:
                response_text = response_text.split('```')[1].strip()
                logger.info("Extracted content from code block")
                
            # Remove any leading/trailing whitespace or quotes
            response_text = response_text.strip('"\'')
            
            # Log a sample of the response for debugging
            logger.info(f"LLM response sample (first 100 chars): {response_text[:100]}...")
            
            # Parse LLM response
            llm_scores = json.loads(response_text)
            logger.info(f"Successfully parsed LLM response with {len(llm_scores)} scored results")
            
            # Create a mapping of result_id to LLM score
            score_map = {
                item["result_id"]: {
                    "llm_score": item["llm_score"],
                    "explanation": item["explanation"]
                }
                for item in llm_scores
            }
            
            # Update results with LLM scores
            for result in results:
                result_id = f"{result.get('file_name')}_{result.get('start_time')}_{result.get('end_time')}"
                if result_id in score_map:
                    result["llm_score"] = score_map[result_id]["llm_score"]
                    result["llm_explanation"] = score_map[result_id]["explanation"]
                    result["final_score"] = 0.4 * result.get("score", 0) + 0.6 * score_map[result_id]["llm_score"]
                else:
                    result["llm_score"] = 0.0
                    result["llm_explanation"] = "Not evaluated by LLM"
                    result["final_score"] = result.get("score", 0)
            
            # Sort by final score
            results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
            
            logger.info(f"LLM reranking completed successfully for {len(results)} results")
            return results
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing LLM reranking response: {str(e)}")
            logger.error(f"Response text that failed to parse: {response_text[:200]}...")
            
            # Try to salvage the response if it looks like it contains JSON arrays
            if '[' in response_text and ']' in response_text:
                try:
                    # Try to extract just the JSON array part
                    array_start = response_text.find('[')
                    array_end = response_text.rfind(']') + 1
                    if array_start >= 0 and array_end > array_start:
                        array_text = response_text[array_start:array_end]
                        logger.info(f"Attempting to parse extracted array: {array_text[:100]}...")
                        llm_scores = json.loads(array_text)
                        logger.info(f"Successfully parsed extracted JSON array with {len(llm_scores)} items")
                        
                        # Continue with the scoring logic
                        score_map = {
                            item["result_id"]: {
                                "llm_score": item["llm_score"],
                                "explanation": item["explanation"]
                            }
                            for item in llm_scores
                        }
                        
                        # Update results with LLM scores
                        for result in results:
                            result_id = f"{result.get('file_name')}_{result.get('start_time')}_{result.get('end_time')}"
                            if result_id in score_map:
                                result["llm_score"] = score_map[result_id]["llm_score"]
                                result["llm_explanation"] = score_map[result_id]["explanation"]
                                result["final_score"] = 0.4 * result.get("score", 0) + 0.6 * score_map[result_id]["llm_score"]
                            else:
                                result["llm_score"] = 0.0
                                result["llm_explanation"] = "Not evaluated by LLM"
                                result["final_score"] = result.get("score", 0)
                        
                        # Sort by final score
                        results.sort(key=lambda x: x.get("final_score", 0), reverse=True)
                        logger.info("Recovered from JSON parse error using array extraction")
                        return results
                except Exception as inner_e:
                    logger.error(f"Failed to recover from JSON parse error: {str(inner_e)}")
            
            # Fallback to original results if we can't parse the LLM response
            logger.info("Falling back to original results without LLM reranking")
            return results
            
    except Exception as e:
        logger.error(f"Error in LLM reranking: {str(e)}")
        return results

async def validate_result_content(result: Dict, query: str, config: LLMConfig_Search) -> Tuple[bool, str]:
    """
    Use LLM to validate if the result's content actually contains information relevant to the query.
    Returns (is_relevant, explanation)
    """
    try:
        if not config.api_key:
            return True, "No LLM validation available"
            
        # Configure the model
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": 0.1,  # Low temperature for consistent validation
                "max_output_tokens": 1024,
                "top_p": 0.95,
                "top_k": 40
            }
        )
        
        # Get the complete transcript using extract_transcript
        file_name = result.get('file_name')
        if not file_name:
            return False, "No file name provided"
            
        try:
            # Get transcript using the extract service
            full_transcript = await extract_transcript(file_name)
            if not full_transcript:
                return False, f"Could not extract transcript for: {file_name}"
                
            # Get the segment's time range for context
            start_time = result.get('start_time')
            end_time = result.get('end_time')
            time_context = f" (focusing on the segment from {format_seconds_to_time(start_time)} to {format_seconds_to_time(end_time)})" if start_time is not None and end_time is not None else ""
            
            # Create a more structured validation prompt
            validation_prompt = """You are a content validation system. Your task is to determine if a transcript contains relevant information to answer a specific query.

Analyze the following transcript and determine if it contains information relevant to the query.
Pay special attention to the segment timing provided, but consider the entire context.

Query: {query}

Full Transcript:
{transcript}

Segment Timing:{time_context}

Instructions:
1. Analyze if this transcript contains information that would help answer the query
2. Consider the entire transcript but focus on the specified time segment
3. Return your response in this exact JSON format:
{{
    "is_relevant": true/false,
    "explanation": "your explanation here",
    "found_in_segment": true/false,
    "relevant_context": "brief quote or summary of the relevant information"
}}

Rules for determining relevance:
- The transcript must contain specific information related to the query
- Just containing similar keywords is not enough
- The information should contribute to answering the query
- If the transcript is completely off-topic, mark as not relevant
- If unsure, lean towards marking as not relevant

Return ONLY the JSON object, no other text or formatting.""".format(
                query=query,
                transcript=full_transcript,
                time_context=time_context
            )
            
            # Get validation from LLM
            response = model.generate_content(validation_prompt)
            response_text = response.text.strip()
            
            # Clean up the response text to ensure it's valid JSON
            # Remove any markdown formatting or extra text
            if '```json' in response_text:
                response_text = response_text.split('```json')[1].split('```')[0].strip()
            elif '```' in response_text:
                response_text = response_text.split('```')[1].strip()
                
            # Remove any leading/trailing whitespace or quotes
            response_text = response_text.strip('"\'')
            
            try:
                validation_result = json.loads(response_text)
                
                # Ensure the response has the required fields
                if not isinstance(validation_result, dict):
                    logger.error(f"Invalid validation result format: {validation_result}")
                    return True, "Invalid validation result format"
                    
                is_relevant = validation_result.get("is_relevant", False)
                explanation = validation_result.get("explanation", "No explanation provided")
                found_in_segment = validation_result.get("found_in_segment", False)
                relevant_context = validation_result.get("relevant_context", "")
                
                # Combine explanation with context
                full_explanation = f"{explanation}\n\nRelevant content: {relevant_context}"
                if found_in_segment:
                    full_explanation += "\n(Found in the specified time segment)"
                else:
                    full_explanation += "\n(Found in other parts of the transcript)"
                
                # Log the successful validation
                logger.info(f"Content validation - Relevant: {is_relevant}, Found in segment: {found_in_segment}")
                
                # Only consider it relevant if the information is found in or near the specified segment
                final_is_relevant = is_relevant and found_in_segment
                
                return final_is_relevant, full_explanation
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM validation response: {response_text}")
                logger.error(f"JSON parse error: {str(e)}")
                
                # Fallback: Try to extract meaning from non-JSON response
                response_lower = response_text.lower()
                
                # Look for clear indicators in the text
                if any(phrase in response_lower for phrase in ['not relevant', 'irrelevant', 'unrelated']):
                    return False, "Content appears not relevant (parsed from non-JSON response)"
                elif any(phrase in response_lower for phrase in ['is relevant', 'contains relevant', 'related to']):
                    return True, "Content appears relevant (parsed from non-JSON response)"
                else:
                    return True, "Unable to parse validation response, defaulting to relevant"
                    
        except Exception as e:
            logger.error(f"Error extracting transcript: {str(e)}")
            return False, f"Error extracting transcript: {str(e)}"
            
    except Exception as e:
        logger.error(f"Error in content validation: {str(e)}")
        return False, f"Validation error: {str(e)}"

async def validate_results_batch(results: List[Dict], query: str, config: LLMConfig_Search) -> List[Dict]:
    """
    Validate a batch of results in parallel using ThreadPoolExecutor.
    
    Args:
        results: List of search results to validate
        query: Original search query
        config: LLM configuration
        
    Returns:
        List of validated results
    """
    if not results:
        return []
        
    validation_stats = {
        "total_validated": 0,
        "relevant_count": 0,
        "irrelevant_count": 0
    }
    
    async def validate_single_result(result: Dict) -> Tuple[Dict, bool]:
        """Validate a single result and return tuple of (result, is_relevant)"""
        is_relevant, explanation = await validate_result_content(result, query, config)
        if is_relevant:
            result["content_validation"] = {
                "is_relevant": True,
                "explanation": explanation
            }
            return result, True
        return result, False
    
    # Create tasks for all results
    tasks = [validate_single_result(result) for result in results]
    
    # Process tasks in parallel with semaphore to limit concurrency
    semaphore = asyncio.Semaphore(MAX_PARALLEL_VALIDATIONS)
    
    async def bounded_validate(task):
        async with semaphore:
            return await task
    
    # Execute all tasks with bounded concurrency
    validated_results = []
    validation_tasks = [bounded_validate(task) for task in tasks]
    
    for result, is_relevant in await asyncio.gather(*validation_tasks):
        validation_stats["total_validated"] += 1
        if is_relevant:
            validation_stats["relevant_count"] += 1
            validated_results.append(result)
        else:
            validation_stats["irrelevant_count"] += 1
            
    logger.info(f"Batch validation complete: {validation_stats}")
    return validated_results, validation_stats

@router.get(
    "/search",
    summary="Search audio transcripts",
    description="Search through audio transcripts using enhanced semantic search"
)
async def search(
    query: str = Query(..., description="Search query"),
    limit: Optional[int] = Query(5, description="Maximum number of results to return"),
    min_confidence: Optional[float] = Query(0.7, description="Minimum confidence threshold (0-1)"),
    min_relevance: Optional[float] = Query(0.5, description="Minimum relevance (combined score) threshold (0-1)"),
    speaker: Optional[int] = Query(None, description="Filter by speaker ID"),
    use_llm_expansion: Optional[bool] = Query(True, description="Use LLM to expand search query"),
    natural_language: Optional[bool] = Query(True, description="Process as natural language query"),
    use_llm_rerank: Optional[bool] = Query(True, description="Use LLM for final reranking"),
    validate_content: Optional[bool] = Query(True, description="Use LLM to validate result content relevance"),
    current_user: dict = Depends(get_current_user)
):
    """
    Search for audio based on transcript content.
    
    This endpoint uses semantic search to find audio files and specific segments
    where the content matches the search query. It can filter results by confidence
    level and speaker, and also supports searching for specific time ranges.
    
    Examples:
    - /search?query=policy discussion
    - /search?query=policy 30-32 (search for "policy" between 30-32 seconds)
    - /search?query=AI&speaker=2 (search for "AI" spoken by speaker 2)
    - /search?query=21&use_llm_expansion=true (will also search for "twenty one", "twenty-one", etc.)
    - /search?query=which audio mentions the meeting on Thursday?&natural_language=true
    """
    try:
        # Initialize LLM config
        config = LLMConfig_Search()
        
        # Log search request
        logger.info(f"Search request - Query: {query}, Limit: {limit}, Natural Language: {natural_language}")
        
        # Store original query for technical term scoring
        original_query = query
        
        # Process as natural language query if specified
        nl_query_info = None
        
        if natural_language:
            try:
                nl_query_info = await process_natural_language_query(query)
                # Use the optimized search query for further processing
                query = nl_query_info.get("search_query", query)
                logger.info(f"Natural language query processed. Optimized query: {query}")
            except Exception as e:
                logger.error(f"Error processing natural language query: {str(e)}")
                # Continue with original query if NL processing fails
                logger.info("Falling back to original query")
                
        # Check if the query contains a timestamp range
        cleaned_query, start_time, end_time = parse_timestamp_range(query)
        
        # Prepare filter dictionary
        filter_dict = {}
        
        if min_confidence:
            filter_dict["confidence"] = {"$gte": min_confidence}
            
        if speaker is not None:
            filter_dict["speaker"] = speaker
            
        # Add time range filter if specified
        if start_time is not None and end_time is not None:
            filter_dict["$and"] = [
                {"start_time": {"$lte": end_time}},
                {"end_time": {"$gte": start_time}}
            ]
        
        # Log filter configuration
        logger.info(f"Search filters: {filter_dict}")
        
        # Use LLM to expand the query if enabled
        expanded_queries = []
        if use_llm_expansion:
            try:
                expanded_queries = await expand_query_with_llm(cleaned_query)
                logger.info(f"Query expanded to: {expanded_queries}")
            except Exception as e:
                logger.error(f"Error expanding query: {str(e)}")
                expanded_queries = [cleaned_query]
                logger.info("Falling back to original query")
        else:
            expanded_queries = [cleaned_query]
            
        # Search for each expanded query using enhanced search
        all_results = []
        seen_ids = set()
        search_errors = []
        pre_filter_count = 0
        
        for expanded_query in expanded_queries:
            try:
                # Use enhanced search for better results
                query_results = await enhanced_search.hybrid_search(
                    query=expanded_query,
                    limit=limit * 2,  # Get more results to account for duplicates
                    filter_dict=filter_dict,
                    original_query=original_query  # Pass original query for technical term scoring
                )
                
                # Add only unique results
                for result in query_results:
                    # Create a unique identifier for the result
                    result_id = f"{result.get('file_name')}_{result.get('start_time')}_{result.get('end_time')}"
                    
                    if result_id not in seen_ids:
                        seen_ids.add(result_id)
                        # Track which expanded query matched this result
                        result["matched_query"] = expanded_query
                        result["original_query"] = original_query  # Add original query for reference
                        # Add exact match flag based on keyword score
                        result["has_exact_match"] = result.get("keyword_score", 0) > 0.5
                        all_results.append(result)
                        
            except Exception as e:
                error_msg = f"Error searching with query '{expanded_query}': {str(e)}"
                logger.error(error_msg)
                search_errors.append(error_msg)
                continue
        
        # Apply relevance threshold to combined scores before any expensive validation/reranking
        if all_results:
            pre_filter_count = len(all_results)
            all_results = [r for r in all_results if r.get("combined_score", 0) >= (min_relevance or 0.0)]
            logger.info(f"Applied min_relevance={min_relevance}: kept {len(all_results)} of {pre_filter_count} candidates")

        if not all_results:
            return {
                "query": original_query,
                "total": 0,
                "results": [],
                "message": "No results met the relevance threshold",
                "search_stats": {
                    "total_candidates": pre_filter_count,
                    "unique_results": len(seen_ids),
                    "queries_attempted": len(expanded_queries),
                    "queries_failed": len(search_errors),
                    "llm_reranking_applied": use_llm_rerank,
                    "content_validation_applied": validate_content,
                    "min_relevance": min_relevance,
                    "min_confidence": min_confidence,
                    "candidates_post_relevance": 0
                }
            }

        # After getting initial results but before final reranking, validate content if enabled
        if validate_content and config.api_key:
            logger.info("Validating result content relevance in parallel...")
            
            # Process results in parallel batches
            validated_results, validation_stats = await validate_results_batch(
                results=all_results,
                query=original_query,
                config=config
            )
            
            # Update results list with only validated results
            all_results = validated_results
            
            logger.info(f"Content validation complete: {validation_stats}")
            
            # If no results remain after validation, return empty with explanation
            if not all_results:
                return {
                    "query": original_query,
                    "total": 0,
                    "results": [],
                    "message": "No results contained relevant information for the query after validation",
                    "validation_stats": validation_stats
                }
        
        # Sort results by combined score
        all_results.sort(key=lambda x: x.get("combined_score", 0), reverse=True)
        
        # Apply LLM reranking if enabled
        if use_llm_rerank and all_results:
            try:
                search_intent = nl_query_info.get("search_intent") if nl_query_info else None
                reranked_results = await llm_rerank_results(
                    results=all_results[:limit*2],  # Rerank top results
                    query=original_query,
                    search_intent=search_intent
                )
                # Take top results after reranking
                results = reranked_results[:limit]
                logger.info("Applied LLM reranking to search results")
            except Exception as e:
                logger.error(f"Error in LLM reranking: {str(e)}")
                # Fallback to original ranking
                results = all_results[:limit]
                logger.info("Using original ranking due to LLM reranking error")
        else:
            results = all_results[:limit]
        
        # Format timestamps in human-readable format
        for result in results:
            if "start_time" in result:
                result["start_time_formatted"] = format_seconds_to_time(result["start_time"])
            if "end_time" in result:
                result["end_time_formatted"] = format_seconds_to_time(result["end_time"])
        
        # Process the results with keyword scoring, technical term recognition
        processed_results = []
        tech_scorer = TechnicalTermsScorer()
        
        for result in results:
            # Always check for embedded_audio_url from podcasts collection
            file_name = result.get("file_name", "")
            if file_name:
                try:
                    # Check podcasts collection for embedded_audio_url using multiple search strategies
                    base_name = file_name.replace('.mp3', '').replace('.wav', '').replace('.m4a', '')
                    
                    # Try multiple query patterns to find the podcast
                    podcast = None
                    
                    # First try exact file_name match
                    podcast = await podcasts_collection.find_one({"file_name": {"$regex": file_name, "$options": "i"}})
                    
                    # If not found, try matching against title field
                    if not podcast:
                        # Create a flexible pattern from the base filename
                        title_pattern = base_name.replace('_', '.*').replace('-', '.*')
                        podcast = await podcasts_collection.find_one({"title": {"$regex": title_pattern, "$options": "i"}})
                    
                    # If still not found, try partial matches on raw_audio_url or embedded_audio_url
                    if not podcast:
                        podcast = await podcasts_collection.find_one({
                            "$or": [
                                {"raw_audio_url": {"$regex": base_name, "$options": "i"}},
                                {"embedded_audio_url": {"$regex": base_name, "$options": "i"}}
                            ]
                        })
                    
                    if podcast and "embedded_audio_url" in podcast and podcast["embedded_audio_url"]:
                        # Store original URL as tmp_url if it's different
                        original_url = result.get("file_url", "")
                        if original_url != podcast["embedded_audio_url"]:
                            result["tmp_url"] = original_url
                        result["file_url"] = podcast["embedded_audio_url"]
                        logger.info(f"Updated file_url for {file_name} to embedded_audio_url")
                    else:
                        # Fallback to find_permanent_url for tmpfiles.org URLs
                        file_url = result.get("file_url", "")
                        if "tmpfiles.org" in file_url:
                            await find_permanent_url(result)
                except Exception as e:
                    logger.error(f"Error updating file_url for {file_name}: {str(e)}")
                    # Fallback to find_permanent_url for tmpfiles.org URLs
                    file_url = result.get("file_url", "")
                    if "tmpfiles.org" in file_url:
                        await find_permanent_url(result)
            
            # Use existing technical and keyword scores if present; otherwise compute minimal fallback
            technical_score = result.get("technical_score")
            if technical_score is None:
                technical_score = tech_scorer.calculate_technical_score(
                    result.get("text", ""), 
                    result.get("original_query", query)
                )
                # Map to 0..1 consistent with EnhancedSearch
                technical_score = max(0.0, min(1.0, technical_score - 1.0))

            keyword_score = result.get("keyword_score")
            if keyword_score is None:
                # Fallback heuristic if keyword_score unavailable
                keyword_score = 1.0 if result.get("has_exact_match", False) else 0.0
            
            # Format result with additional scores
            processed_result = {
                "text": result.get("text", ""),
                "file_name": result.get("file_name", ""),
                "file_url": result.get("file_url", ""),  # Use the result's file_url which may have been updated
                "start_time": result.get("start_time", 0),
                "end_time": result.get("end_time", 0),
                "confidence": result.get("confidence", 0),
                # Provide both normalized and raw semantic scores when available
                "semantic_score": result.get("semantic_score", result.get("semantic_score_raw", 0)),
                "semantic_score_raw": result.get("semantic_score_raw", None),
                "original_query": original_query,
                "combined_score": result.get("combined_score", 0),
                "keyword_score": keyword_score,
                "technical_score": technical_score
            }
            
            # Add tmp_url if present in the result
            if result.get("tmp_url"):
                processed_result["tmp_url"] = result.get("tmp_url")
            
            processed_results.append(processed_result)
        
        response_data = {
            "query": original_query,
            "cleaned_query": cleaned_query if cleaned_query != original_query else None,
            "expanded_queries": expanded_queries if use_llm_expansion else None,
            "time_range": {
                "start": start_time,
                "end": end_time,
                "start_formatted": format_seconds_to_time(start_time) if start_time is not None else None,
                "end_formatted": format_seconds_to_time(end_time) if end_time is not None else None
            } if start_time is not None else None,
            "total": len(results),
            "exact_matches": sum(1 for r in results if r.get("has_exact_match", False)),
            "results": processed_results,
            "search_errors": search_errors if search_errors else None,
            "search_stats": {
                "total_candidates": pre_filter_count or len(all_results),
                "unique_results": len(seen_ids),
                "queries_attempted": len(expanded_queries),
                "queries_failed": len(search_errors),
                "llm_reranking_applied": use_llm_rerank,
                "content_validation_applied": validate_content,
                "min_relevance": min_relevance,
                "min_confidence": min_confidence,
                "candidates_post_relevance": len(all_results)
            }
        }
        
        # Add validation stats if content validation was performed
        if validate_content and config.api_key:
            response_data["validation_stats"] = validation_stats
        
        # Add natural language processing info if available
        if nl_query_info:
            response_data["natural_language_analysis"] = nl_query_info
        
        # Log search completion
        logger.info(f"Search completed - Found {len(results)} results from {len(all_results)} candidates")
        
        # Track search term
        track_search_term(query, user_id=str(current_user.get("_id", "")))
        
        # Track user activity if user is authenticated
        if current_user and "_id" in current_user:
            track_user_activity(
                user_id=str(current_user.get("_id", "")),
                feature="search",
                additional_data={
                    "query": query,
                    "results_count": len(results),
                    "total_candidates": len(all_results)
                }
            )
        
        return response_data
        
    except Exception as e:
        error_msg = f"Error searching transcripts: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

def format_seconds_to_time(seconds: float) -> str:
    """
    Format seconds as HH:MM:SS or MM:SS
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted time string
    """
    if seconds is None:
        return None
        
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    else:
        return f"{minutes:02d}:{secs:06.3f}"

class AnswerRequest(BaseModel):
    query: str
    transcript: str

@router.post(
    "/generate-answer",
    summary="Generate answer from transcript and query",
    description="Generate an answer to a user query based on transcript content using LLM"
)
async def generate_answer(
    request: AnswerRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate an answer to a user query based on transcript content.
    
    This endpoint uses an LLM to analyze the transcript content and generate
    a relevant answer to the user's question based solely on the information
    in the transcript.
    
    Example body:
    {
        "query": "Artemis I is described as the first uncrewed test flight of the integrated SLS and Orion system. Based on the transcript, how does this mission serve both engineering and scientific purposes simultaneously?",
        "transcript": "The complete transcript text from the audio file..."
    }
    """
    try:
        config = LLMConfig_Search()
        
        if not config.api_key:
            raise HTTPException(status_code=500, detail="LLM API key not configured")
        
        # Validate input
        if not request.query:
            raise HTTPException(status_code=400, detail="Query is required")
        
        if not request.transcript:
            raise HTTPException(status_code=400, detail="Transcript is required")
            
        # Configure the LLM
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": 0.3,  # Slightly higher temperature for more natural answers
                "max_output_tokens": 1024,  # Allow longer answers
                "top_p": 0.95,
                "top_k": 40
            }
        )
        
        # Format the prompt with the transcript and query
        formatted_prompt = config.answer_generation_prompt.format(
            transcript=request.transcript,
            query=request.query
        )
        
        # Generate the answer
        response = model.generate_content(formatted_prompt)
        
        # Return the generated answer
        return {
            "query": request.query,
            "answer": response.text,
            "model": config.model_name,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating answer: {str(e)}")

class SearchAndAnswerRequest(BaseModel):
    search_query: str 
    result_id: str
    transcript: str
    # Optional conversational context from the frontend chat UI
    history: Optional[List[Dict[str, str]]] = None
    context: Optional[str] = None

@router.post(
    "/search-and-answer",
    summary="Search and generate answer in one request",
    description="Generates an answer for a specific search result without requiring separate requests"
)
async def search_and_answer(
    request: SearchAndAnswerRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Generate an answer for a specific search result without requiring a separate request.
    This helps avoid UI refreshes in the frontend.
    
    Example body:
    {
        "search_query": "How does plants grow in lunar soil?",
        "result_id": "file123_10.5_20.8",
        "transcript": "The transcript text from the result..."
    }
    """
    try:
        # Debug logging
        log_info("Search and answer request received", "search.search_and_answer", {"search_query": request.search_query, "result_id": request.result_id})
        if request.transcript:
            transcript_len = len(request.transcript)
            transcript_words = len(request.transcript.split())
            log_info(f"Processing transcript with {transcript_len} chars, {transcript_words} words", "search.search_and_answer", {"transcript_length": transcript_len, "transcript_words": transcript_words})
        else:
            log_warning("Empty transcript received", "search.search_and_answer")
        
        config = LLMConfig_Search()
        
        if not config.api_key:
            log_error("LLM API key not configured", "search.search_and_answer")
            raise HTTPException(status_code=500, detail="LLM API key not configured")
            
        # Validate the transcript
        if not request.transcript or len(request.transcript.strip()) < 10:
            log_error("Transcript too short or empty", "search.search_and_answer", {"transcript_length": len(request.transcript.strip()) if request.transcript else 0})
            return {
                "result_id": request.result_id,
                "search_query": request.search_query,
                "answer": "Error: The transcript is too short or empty. Cannot generate an answer.",
                "model": config.model_name,
            }
            
        # Log transcript length for debugging
        transcript_word_count = len(request.transcript.split())
        log_info(f"Processing answer for '{request.search_query}' with transcript of {transcript_word_count} words", "search.search_and_answer", {"search_query": request.search_query, "transcript_word_count": transcript_word_count})
        
        # Configure the LLM
        model = genai.GenerativeModel(
            model_name=config.model_name,
            generation_config={
                "temperature": 0.2,  # Lower temperature for more factual answers
                "max_output_tokens": 1024,  # Allow longer answers
                "top_p": 0.95,
                "top_k": 40
            }
        )
        
        # Base prompt with transcript and current query
        formatted_prompt = config.answer_generation_prompt.format(
            transcript=request.transcript,
            query=request.search_query
        )

        # Append conversation history and optional context (if provided)
        history_block = ""
        if request.history:
            try:
                # Limit to last 10 messages to control prompt size
                recent = request.history[-10:]
                history_lines = []
                for m in recent:
                    role = (m.get('role') or 'user').strip()
                    content = (m.get('content') or '').strip()
                    if content:
                        history_lines.append(f"{role}: {content}")
                if history_lines:
                    history_block = "\n\nConversation history (for coherence, do not add facts not in transcript):\n" + "\n".join(history_lines)
            except Exception as e:
                log_warning(f"Failed to format history for prompt: {str(e)}", "search.search_and_answer")

        context_block = ""
        if request.context:
            context_block = f"\n\nAdditional context from UI: {request.context}"

        full_prompt = formatted_prompt + history_block + context_block
        
        log_info(f"Sending prompt to LLM (length: {len(full_prompt)} chars)", "search.search_and_answer", {"prompt_length": len(full_prompt)})
        
        # Generate the answer
        response = model.generate_content(full_prompt)
        
        log_info(f"LLM response received (length: {len(response.text)} chars)", "search.search_and_answer", {"response_length": len(response.text)})
        
        # Return the generated answer along with identifying information
        return {
            "result_id": request.result_id,
            "search_query": request.search_query,
            "answer": response.text,
            "model": config.model_name,
        }
        
    except Exception as e:
        log_error(f"Error generating answer: {str(e)}", "search.search_and_answer", {"error": str(e), "search_query": request.search_query if 'request' in locals() else "unknown"})
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating answer: {str(e)}")

@router.get(
    "/test-connection",
    summary="Test Pinecone connection",
    description="Test the connection to Pinecone and check index status"
)
async def test_connection():
    """Test the connection to Pinecone and check index status"""
    try:
        test_pinecone_connection()
        return {"status": "completed", "message": "Check the logs for details"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing connection: {str(e)}")

async def find_permanent_url(result: Dict) -> None:
    """
    Find a permanent Supabase URL for a result with a temporary URL.
    Updates the result in place if a permanent URL is found.
    
    Args:
        result: The search result to update
    """
    file_url = result.get("file_url", "")
    file_name = result.get("file_name", "")
    
    if not file_name or not "tmpfiles.org" in file_url:
        return
        
    try:
        # First check podcasts collection for embedded_audio_url
        podcast = await podcasts_collection.find_one({"file_name": {"$regex": file_name}})
        if podcast and "embedded_audio_url" in podcast and podcast["embedded_audio_url"]:
            result["file_url"] = podcast["embedded_audio_url"]
            # Store the temporary URL as tmp_url if not already present
            if not result.get("tmp_url"):
                result["tmp_url"] = file_url
            return
            
        # Try uploads collection
        upload = await uploads_collection.find_one({"file_name": {"$regex": file_name}})
        if upload and "supabase_url" in upload and upload["supabase_url"]:
            result["file_url"] = upload["supabase_url"]
            # Store the temporary URL as tmp_url if not already present
            if not result.get("tmp_url"):
                result["tmp_url"] = file_url
            return
            
        # If we get here, no permanent URL was found
        logger.warning(f"No permanent URL found for file: {file_name}")
    except Exception as e:
        logger.error(f"Error finding permanent URL: {str(e)}") 
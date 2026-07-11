import { useState, useEffect, useRef } from 'react'
import { Moon, CloudRain, Aperture, BrainCircuit, Heart, Sunrise, Flame, Sparkles, Mountain, Smile } from 'lucide-react'

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const SUGGESTED_QUERIES = [
  "I want something bittersweet but hopeful.",
  "A rainy Sunday movie.",
  "Something like Blade Runner but quieter.",
  "Movies that make me feel insignificant in the universe."
];

const CINEMATIC_QUOTES = [
  "Every film begins with a feeling.",
  "What do you want to experience tonight?",
  "Some stories find you."
];

const MOOD_PILLS = [
  { icon: Moon, label: "Quiet loneliness", query: "A quiet, melancholic movie about loneliness and solitude." },
  { icon: CloudRain, label: "Rainy night", query: "A moody, atmospheric movie perfect for a rainy night." },
  { icon: Aperture, label: "Beautiful cinematography", query: "A visually stunning movie with gorgeous cinematography and direction." },
  { icon: BrainCircuit, label: "Mind-bending", query: "Existential and mind-bending sci-fi about time travel or space." },
  { icon: Heart, label: "Found family", query: "A heartwarming story about unexpected friendships and found family." },
  { icon: Sunrise, label: "Gentle optimism", query: "A feel-good, uplifting movie with gentle optimism." },
  { icon: Flame, label: "Slow burn mystery", query: "A slow-burn atmospheric mystery with an unsettling vibe." },
  { icon: Sparkles, label: "Dreamlike romance", query: "A surreal, dreamy romance movie that feels like a fantasy." },
  { icon: Mountain, label: "Big adventure", query: "An epic adventure film with breathtaking landscapes." },
  { icon: Smile, label: "Feel-good, not cheesy", query: "An intelligent, heartwarming comedy-drama that isn't cheesy." },
];

const HOVER_TRANSITION = "transition-all duration-[250ms] ease-[cubic-bezier(0.22,1,0.36,1)]";


export default function App() {
  const [state, setState] = useState({
    query: "",
    expandedQuery: "",
    results: [],
    loading: false,
    error: null,
    selectedMovie: null,
    activeSuggestion: null,
    recentSearches: [],
    watchlist: [],
    featuredFilm: null,
    spotifyUrl: "",
    spotifyLoading: false,
    ui: {
      heroCollapsed: false,
      detailOpen: false,
      spotifyOpen: false
    }
  });

  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [fadePlaceholder, setFadePlaceholder] = useState(true);
  const [homepageQuote, setHomepageQuote] = useState("");
  const [headerScrolled, setHeaderScrolled] = useState(false);

  const textareaRef = useRef(null);
  const debounceTimerRef = useRef(null);

  const updateState = (updates) => {
    setState((prev) => {
      let nextUi = prev.ui;
      if (updates.ui !== undefined) {
        nextUi = { ...prev.ui, ...updates.ui };
      }
      return { ...prev, ...updates, ui: nextUi };
    });
  };

  useEffect(() => {
    setHomepageQuote(CINEMATIC_QUOTES[Math.floor(Math.random() * CINEMATIC_QUOTES.length)]);
    
    const timer = setInterval(() => {
      setFadePlaceholder(false);
      setTimeout(() => {
        setPlaceholderIndex((prev) => (prev + 1) % SUGGESTED_QUERIES.length);
        setFadePlaceholder(true);
      }, 300);
    }, 5500);

    fetch(`${API_BASE_URL}/featured`)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data) updateState({ featuredFilm: data });
      })
      .catch(err => console.warn("Could not fetch featured film:", err));

    try {
      const savedSearches = sessionStorage.getItem('cinemate_recent_searches');
      if (savedSearches) {
        updateState({ recentSearches: JSON.parse(savedSearches) });
      }
    } catch (e) {
      console.warn("Could not parse recent searches from session.");
    }

    const handleScroll = () => setHeaderScrolled(window.scrollY > 20);
    window.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      clearInterval(timer);
      window.removeEventListener('scroll', handleScroll);
    };
  }, []);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  }, [state.query]);

  const performSearch = async (searchQuery) => {
    if (!searchQuery || searchQuery.trim().length === 0) return;
    
    updateState({ 
      loading: true, 
      error: null, 
      ui: { heroCollapsed: true } 
    });

    try {
      const response = await fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(searchQuery)}&limit=8`);
      if (!response.ok) {
        throw new Error("Failed to communicate with CineMate search engine.");
      }
      const data = await response.json();
      
      setState(prev => {
        const newSearches = prev.recentSearches.includes(searchQuery)
          ? prev.recentSearches
          : [searchQuery, ...prev.recentSearches].slice(0, 5);
          
        sessionStorage.setItem('cinemate_recent_searches', JSON.stringify(newSearches));

        return {
          ...prev,
          results: data.results || [],
          loading: false,
          recentSearches: newSearches,
          ui: { ...prev.ui, heroCollapsed: true }
        };
      });
    } catch (err) {
      updateState({
        error: err.message || "An unexpected error occurred.",
        results: [],
        loading: false
      });
    }
  };

  const handleSpotifySync = async () => {
    const url = state.spotifyUrl;
    if (!url || url.trim().length === 0) return;
    
    updateState({ 
      spotifyLoading: true, 
      error: null 
    });

    try {
      const response = await fetch(`${API_BASE_URL}/search/spotify?url=${encodeURIComponent(url)}&limit=8`);
      if (!response.ok) {
        throw new Error("Failed to process Spotify playlist.");
      }
      const data = await response.json();
      
      setState(prev => {
        return {
          ...prev,
          query: data.query, // Set the mapped mood as the search query
          results: data.results || [],
          loading: false,
          spotifyLoading: false,
          ui: { ...prev.ui, heroCollapsed: true, spotifyOpen: false }
        };
      });
    } catch (err) {
      updateState({
        error: err.message || "An unexpected error occurred.",
        results: [],
        loading: false,
        spotifyLoading: false,
        ui: { ...state.ui, spotifyOpen: false }
      });
    }
  };

  const handleTextareaChange = (e) => {
    const val = e.target.value;
    updateState({ query: val });

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    if (val.trim().length > 3) {
      debounceTimerRef.current = setTimeout(() => {
        performSearch(val);
      }, 300);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
      performSearch(state.query);
    }
  };

  const handleSuggestionClick = (suggestion) => {
    updateState({ query: suggestion });
    performSearch(suggestion);
  };

  const handleClear = () => {
    updateState({
      query: "",
      results: [],
      error: null,
      ui: { heroCollapsed: false }
    });
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  };

  const handleMovieSelect = (movie) => {
    updateState({
      selectedMovie: movie,
      ui: { detailOpen: !!movie }
    });
  };

  const toggleWatchlist = (e, movie) => {
    e.stopPropagation();
    setState(prev => {
      const isSaved = prev.watchlist.some(m => m.id === movie.id);
      return {
        ...prev,
        watchlist: isSaved 
          ? prev.watchlist.filter(m => m.id !== movie.id)
          : [...prev.watchlist, movie]
      };
    });
  };

  const handleFindSimilar = (e, movie) => {
    e.stopPropagation();
    const q = movie.keywords?.slice(0, 4).join(', ') || movie.title;
    handleSuggestionClick(`Something matching the themes of ${q}`);
  };

  const getRatingStars = (rating) => {
    const filledCount = Math.round((rating || 0) / 2);
    return "★".repeat(filledCount) + "☆".repeat(5 - filledCount);
  };

  // ─── RENDER ──────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-brand-bg text-brand-text-primary selection:bg-brand-highlight/30 selection:text-white flex flex-col">
      
      {/* Loading Overlay */}
      {state.loading && (
        <div className="fixed inset-0 pointer-events-none z-50 overflow-hidden">
          <div className="absolute top-0 left-1/4 w-1/2 h-[500px] bg-gradient-to-b from-brand-highlight/8 to-transparent blur-[120px] origin-top animate-[spin_10s_linear_infinite]" />
        </div>
      )}

      {/* ─── FLOATING HEADER ──────────────────────────────── */}
      <header className="fixed inset-x-0 top-0 z-50 flex justify-center px-6 pt-4">
        <nav className={`w-full max-w-6xl flex items-center justify-between px-8 py-3.5 rounded-2xl border ${HOVER_TRANSITION} ${
          headerScrolled 
            ? 'bg-brand-bg/80 backdrop-blur-xl border-brand-divider shadow-[0_8px_32px_rgba(0,0,0,0.4)]' 
            : 'bg-transparent border-transparent'
        }`}>
          {/* Left: Wordmark */}
          <div
            className="cursor-pointer focus:outline-none rounded-lg"
            onClick={handleClear}
            tabIndex={0}
            onKeyDown={(e) => { if(e.key === 'Enter' || e.key === ' ') handleClear(); }}
          >
            <span className="font-serif text-[22px] tracking-[0.12em] text-brand-text-primary font-medium hover:text-brand-accent transition-colors duration-250">
              CineMate
            </span>
          </div>

          {/* Center: Nav Links — 16px */}
          <div className="hidden md:flex items-center gap-9">
            {['Explore', 'Collections', 'Watchlist'].map(link => (
              <button
                key={link}
                className="text-base uppercase tracking-[0.12em] font-sans text-brand-text-secondary hover:text-brand-text-primary transition-colors duration-250 focus:outline-none"
                onClick={() => {
                  if (link === 'Explore') {
                    handleClear();
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }
                }}
              >
                {link}
              </button>
            ))}
            <button
              className={`group flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-brand-divider/40 bg-brand-surface/30 text-xs uppercase tracking-[0.12em] font-sans text-brand-text-secondary/60 hover:text-[#1DB954] hover:border-[#1DB954]/30 hover:bg-[#1DB954]/5 ${HOVER_TRANSITION} focus:outline-none`}
              onClick={() => updateState({ ui: { spotifyOpen: true } })}
            >
              <svg className="w-3.5 h-3.5 text-[#5a7a6a] group-hover:text-[#1DB954] transition-colors duration-250" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.54.659.301 1.02zm1.44-3.3c-.301.42-.84.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.84.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.6.18-1.2.72-1.38 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.239.54-.959.72-1.56.3z"/></svg>
              Sync
            </button>
          </div>

          {/* Right: Search icon + Profile */}
          <div className="flex items-center gap-5">
            {(headerScrolled || state.ui.heroCollapsed) && (
              <button 
                className="text-brand-text-secondary hover:text-brand-text-primary transition-colors duration-250 focus:outline-none p-1"
                onClick={() => textareaRef.current?.focus()}
                aria-label="Focus search"
              >
                <svg className="w-[18px] h-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
                </svg>
              </button>
            )}
            <div className="w-8 h-8 rounded-full bg-brand-surface border border-brand-divider flex items-center justify-center">
              <svg className="w-4 h-4 text-brand-text-secondary/60" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0ZM4.501 20.118a7.5 7.5 0 0 1 14.998 0A17.933 17.933 0 0 1 12 21.75c-2.676 0-5.216-.584-7.499-1.632Z" />
              </svg>
            </div>
          </div>
        </nav>
      </header>

      {/* ─── MAIN CONTENT ─────────────────────────────────── */}
      <main className="w-full flex flex-col flex-grow pt-24">

        {/* ─── HERO SECTION (Split Layout) ────────────────── */}
        {!state.ui.heroCollapsed && (
          <section className="w-full max-w-7xl mx-auto px-8 md:px-12 pt-8 pb-10 relative">
            {/* Radial glow behind hero */}
            <div className="radial-glow" style={{ top: '-100px', left: '10%' }} />

            <div className="relative z-10 flex flex-col lg:flex-row items-start gap-14 lg:gap-16">
              
              {/* Left: Editorial copy + Search */}
              <div className="flex-1 max-w-2xl pt-4">
                <h1 className="font-serif text-[3.2rem] md:text-[3.6rem] lg:text-[4rem] text-brand-text-primary font-medium leading-[1.12] tracking-tight mb-6">
                  Find the right movie for your mood.
                </h1>
                <p className="font-serif italic text-brand-text-secondary text-lg md:text-xl mb-10 max-w-md leading-relaxed">
                  {homepageQuote}
                </p>

                {/* Search Box */}
                <div className="relative">
                  <div className={`relative bg-brand-surface/80 border border-brand-divider rounded-2xl hover:border-brand-text-secondary/25 focus-within:border-brand-highlight/40 focus-within:shadow-[0_0_40px_rgba(74,111,165,0.1)] ${HOVER_TRANSITION}`}>
                    <textarea
                      ref={textareaRef}
                      rows={1}
                      value={state.query}
                      onChange={handleTextareaChange}
                      onKeyDown={handleKeyDown}
                      placeholder=""
                      maxLength={500}
                      aria-label="Describe the movie you're looking for"
                      className="w-full bg-transparent resize-none overflow-hidden outline-none text-brand-text-primary font-sans placeholder-transparent focus:ring-0 leading-relaxed py-6 pl-6 pr-24 text-lg rounded-2xl"
                      style={{ minHeight: '72px' }}
                    />

                    {!state.query && (
                      <div 
                        className={`absolute pointer-events-none text-brand-text-secondary/60 font-sans left-6 top-[24px] text-lg transition-opacity duration-300 ${
                          fadePlaceholder ? 'opacity-100' : 'opacity-0'
                        }`}
                        aria-hidden="true"
                      >
                        {SUGGESTED_QUERIES[placeholderIndex]}
                      </div>
                    )}

                    <div className="absolute flex items-center gap-3 text-brand-text-secondary right-5 bottom-5">
                      {state.query && (
                        <button 
                          onClick={handleClear} 
                          className="p-1 hover:text-brand-accent transition-colors duration-250 focus:outline-none rounded-lg"
                          title="Clear search"
                          aria-label="Clear search"
                        >
                          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      )}
                      <span className="text-xs font-mono opacity-50 select-none tracking-wider">
                        {state.query.length}/500
                      </span>
                      <button
                        onClick={() => performSearch(state.query)}
                        disabled={!state.query.trim()}
                        className="p-1.5 text-brand-text-primary hover:text-brand-accent disabled:opacity-20 transition-colors duration-250 focus:outline-none rounded-lg"
                        title="Search (Ctrl + Enter)"
                        aria-label="Execute search"
                      >
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                        </svg>
                      </button>
                    </div>
                  </div>

                  <div className="mt-3 flex justify-between text-xs text-brand-text-secondary/60 px-1 select-none tracking-wide">
                    <span>Press <kbd className="font-mono text-brand-text-primary/60">Ctrl + Enter</kbd> to search</span>
                    <span>Type natural sentences</span>
                  </div>
                </div>
              </div>

              {/* Right: Featured Film of the Day Card */}
              {state.featuredFilm && (
                <div 
                  className={`flex-shrink-0 w-full lg:w-[420px] cursor-pointer group relative rounded-2xl overflow-hidden border border-brand-divider/40 bg-brand-surface/40 shadow-[0_16px_48px_-12px_rgba(0,0,0,0.5)] hover:shadow-[0_20px_56px_-8px_rgba(0,0,0,0.6)] hover:border-brand-divider/60 ${HOVER_TRANSITION}`}
                  onClick={() => handleMovieSelect(state.featuredFilm)}
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') handleMovieSelect(state.featuredFilm); }}
                >
                  {/* Poster */}
                  <div className="relative aspect-[16/10] overflow-hidden">
                    <img 
                      src={state.featuredFilm.backdrop_url || state.featuredFilm.poster_url} 
                      alt={state.featuredFilm.title} 
                      className={`w-full h-full object-cover brightness-[0.6] group-hover:brightness-[0.75] group-hover:scale-[1.03] transition-all duration-700 ease-out`}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-brand-surface via-transparent to-transparent pointer-events-none" />
                  </div>

                  {/* Card Content */}
                  <div className="p-6 pt-4">
                    <span className="text-xs tracking-[0.2em] uppercase font-mono text-brand-highlight block mb-3">
                      Featured Film of the Day
                    </span>
                    <h3 className="font-serif text-2xl text-brand-text-primary mb-2 leading-tight">
                      {state.featuredFilm.title}
                    </h3>
                    
                    {/* Rating */}
                    <div className="flex items-center gap-3 mb-3 text-sm">
                      <span className="text-brand-accent tracking-wider">{getRatingStars(state.featuredFilm.rating)}</span>
                      <span className="text-brand-text-secondary">{state.featuredFilm.rating?.toFixed(1)}/10</span>
                    </div>

                    {/* Description */}
                    <p className="text-[15px] text-brand-text-secondary leading-relaxed line-clamp-2 mb-3">
                      {state.featuredFilm.overview}
                    </p>

                    {/* Why selected */}
                    <p className="text-xs text-brand-highlight/80 italic font-serif">
                      {state.featuredFilm.match_reason || "Handpicked for its cinematic excellence and timeless appeal."}
                    </p>
                  </div>
                </div>
              )}
            </div>
          </section>
        )}

        {/* ─── COLLAPSED SEARCH BAR (Results Mode) ────────── */}
        {state.ui.heroCollapsed && (
          <section className="sticky top-0 bg-brand-bg/90 backdrop-blur-xl py-4 z-30 border-b border-brand-divider">
            <div className="w-full max-w-7xl mx-auto px-8 md:px-12">
              <div className="relative bg-brand-surface/60 border border-brand-divider rounded-2xl focus-within:border-brand-highlight/40">
                <textarea
                  ref={textareaRef}
                  rows={1}
                  value={state.query}
                  onChange={handleTextareaChange}
                  onKeyDown={handleKeyDown}
                  placeholder=""
                  maxLength={500}
                  aria-label="Search for a movie"
                  className="w-full bg-transparent resize-none overflow-hidden outline-none text-brand-text-primary font-sans placeholder-transparent focus:ring-0 leading-relaxed py-4 pl-6 pr-20 text-base md:text-lg rounded-2xl"
                  style={{ minHeight: '56px' }}
                />

                {!state.query && (
                  <div 
                    className={`absolute pointer-events-none text-brand-text-secondary/60 font-sans left-6 top-[16px] text-base md:text-lg transition-opacity duration-300 ${
                      fadePlaceholder ? 'opacity-100' : 'opacity-0'
                    }`}
                    aria-hidden="true"
                  >
                    {SUGGESTED_QUERIES[placeholderIndex]}
                  </div>
                )}

                <div className="absolute flex items-center gap-3 text-brand-text-secondary right-4 bottom-3.5">
                  {state.query && (
                    <button 
                      onClick={handleClear} 
                      className="p-1 hover:text-brand-accent transition-colors duration-250 focus:outline-none rounded-lg"
                      title="Clear search"
                      aria-label="Clear search"
                    >
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  )}
                  <span className="text-xs font-mono opacity-50 select-none tracking-wider">
                    {state.query.length}/500
                  </span>
                  <button
                    onClick={() => performSearch(state.query)}
                    disabled={!state.query.trim()}
                    className="p-1 text-brand-text-primary hover:text-brand-accent disabled:opacity-20 transition-colors duration-250 focus:outline-none rounded-lg"
                    title="Search (Ctrl + Enter)"
                    aria-label="Execute search"
                  >
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                    </svg>
                  </button>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* ─── DYNAMIC CONTENT AREA ───────────────────────── */}
        <section className="w-full max-w-7xl mx-auto px-8 md:px-12 flex-grow">
          
          {/* Skeleton Loader */}
          {state.loading && (
            <div className="space-y-5 py-10">
              {[1, 2, 3].map((n) => (
                <div key={n} className="flex gap-8 p-7 bg-brand-surface/20 border border-brand-divider/20 animate-shimmer rounded-2xl">
                  <div className="w-[22%] aspect-[2/3] bg-brand-surface/30 rounded-xl" />
                  <div className="flex-1 space-y-4 py-2">
                    <div className="h-7 bg-brand-surface/30 w-1/3 rounded-lg" />
                    <div className="h-5 bg-brand-surface/30 w-3/4 rounded-lg" />
                    <div className="h-16 bg-brand-surface/30 w-full rounded-lg" />
                    <div className="h-4 bg-brand-surface/30 w-1/4 mt-auto rounded-lg" />
                  </div>
                </div>
              ))}
            </div>
          )}

          {state.error && !state.loading && (
            <div className="bg-brand-surface/50 border border-brand-divider p-8 text-center max-w-xl mx-auto my-12 rounded-2xl">
              <p className="text-brand-accent font-serif mb-3 text-lg">System Error</p>
              <p className="text-base text-brand-text-secondary">{state.error}</p>
            </div>
          )}

          {/* ─── HOMEPAGE: Mood Pills + Recent Searches ───── */}
          {!state.ui.heroCollapsed && !state.loading && !state.error && (
            <div className="space-y-14 pb-16 pt-4">
              
              {/* Recent Searches */}
              {state.recentSearches.length > 0 && (
                <div>
                  <span className="text-xs tracking-[0.2em] uppercase text-brand-text-secondary/70 font-mono block mb-5">
                    Recent Searches
                  </span>
                  <div className="flex flex-wrap gap-3">
                    {state.recentSearches.map((search, idx) => (
                      <button
                        key={idx}
                        onClick={() => handleSuggestionClick(search)}
                        className={`text-[15px] border border-brand-divider px-5 py-2.5 text-brand-text-secondary rounded-xl hover:bg-brand-surface/50 hover:text-brand-text-primary hover:border-brand-highlight/30 focus:outline-none ${HOVER_TRANSITION}`}
                      >
                        {search}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Explore — Mood Pills */}
              <div>
                <span className="text-xs tracking-[0.2em] uppercase text-brand-text-secondary/70 font-mono block mb-6">
                  Explore by Mood
                </span>
                <div className="flex flex-wrap gap-3">
                  {MOOD_PILLS.map((mood, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSuggestionClick(mood.query)}
                      className={`group flex items-center gap-2.5 px-5 py-3 rounded-full border border-brand-divider/60 bg-brand-surface/30 text-brand-text-secondary hover:text-brand-text-primary hover:bg-brand-surface/60 hover:border-brand-highlight/40 hover:-translate-y-[2px] hover:shadow-[0_6px_20px_-6px_rgba(74,111,165,0.15)] focus:outline-none ${HOVER_TRANSITION}`}
                      style={{ animation: `fade-in-up 0.4s ease-out both`, animationDelay: `${idx * 0.04}s` }}
                    >
                      <mood.icon size={16} strokeWidth={1.5} className={`shrink-0 group-hover:scale-110 ${HOVER_TRANSITION}`} />
                      <span className="text-[15px] font-sans tracking-wide">{mood.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Stats Strip */}
              <div className="pt-6 border-t border-brand-divider/20 flex flex-col md:flex-row justify-between items-center text-[11px] uppercase tracking-[0.2em] font-mono text-brand-text-secondary/40 gap-3">
                <div>Powered by TMDB</div>
                <div>Semantic Search</div>
              </div>
            </div>
          )}

          {/* ─── NO RESULTS ───────────────────────────────── */}
          {state.ui.heroCollapsed && state.results.length === 0 && !state.loading && !state.error && (
            <div className="text-center max-w-2xl mx-auto py-20 space-y-6">
              <div className="text-brand-text-primary text-3xl font-serif">We couldn't find a match.</div>
              
              <div className="space-y-2 text-base text-brand-text-secondary pb-6">
                <p>Try describing a feeling instead of a genre.</p>
                <p>Search for an emotion, a memory, or an atmosphere.</p>
              </div>

              <div className="pt-6 border-t border-brand-divider flex flex-wrap justify-center gap-3">
                {MOOD_PILLS.slice(0, 6).map((mood, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSuggestionClick(mood.query)}
                    className={`text-[15px] border border-brand-divider px-5 py-2.5 rounded-full hover:bg-brand-surface/50 hover:text-brand-text-primary hover:border-brand-highlight/30 transition-colors duration-250 focus:outline-none`}
                  >
                    <mood.icon size={16} strokeWidth={1.5} className="inline-block align-[-2px] mr-1.5" />{mood.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* ─── SEARCH RESULTS ───────────────────────────── */}
          {state.ui.heroCollapsed && state.results.length > 0 && !state.loading && !state.error && (
            <div className="space-y-8 py-10">
              
              <div className="pb-4">
                <span className="text-brand-text-secondary font-serif text-lg italic tracking-wide">
                  Showing the closest cinematic matches for your mood.
                </span>
              </div>

              <div className="space-y-5">
                {state.results.map((movie, index) => {
                  return (
                    <article
                      key={movie.id}
                      onClick={() => handleMovieSelect(movie)}
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          handleMovieSelect(movie);
                        }
                      }}
                      className={`group flex flex-col md:flex-row gap-7 md:gap-8 cursor-pointer relative p-6 md:p-7 border border-brand-divider/30 bg-brand-surface/10 hover:bg-brand-surface/30 hover:border-brand-divider/50 hover:shadow-[0_12px_40px_-10px_rgba(0,0,0,0.5)] rounded-2xl hover:-translate-y-[2px] focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-highlight/50 will-change-transform ${HOVER_TRANSITION}`}
                      style={{
                        animation: `slide-up-fade 0.5s ease-out both`,
                        animationDelay: `${index * 0.08}s`
                      }}
                    >
                      {/* Poster */}
                      <div className="w-full md:w-[20%] shrink-0 flex flex-col gap-2.5">
                        <div className={`w-full aspect-[2/3] bg-brand-surface rounded-xl border border-brand-divider/40 overflow-hidden relative shadow-md group-hover:shadow-xl ${HOVER_TRANSITION}`}>
                          {movie.poster_url ? (
                            <>
                              <img
                                src={movie.poster_url}
                                alt={movie.title}
                                className={`w-full h-full object-cover brightness-[0.88] group-hover:brightness-95 group-hover:scale-[1.03] will-change-transform transition-all duration-500 ease-out`}
                                loading="lazy"
                              />
                              <div className="absolute inset-0 shadow-[inset_0_0_20px_rgba(0,0,0,0.25)] pointer-events-none rounded-xl" />
                            </>
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-sm tracking-widest text-brand-text-secondary/50 uppercase">
                              No Poster
                            </div>
                          )}
                        </div>
                        {/* Rating + Match */}
                        <div className={`flex items-center justify-between w-full text-brand-text-secondary group-hover:text-brand-text-primary px-0.5 ${HOVER_TRANSITION}`}>
                          <span className="text-sm tracking-wider" title={`Rating: ${movie.rating?.toFixed(1)}/10`}>{getRatingStars(movie.rating)}</span>
                          <span className="text-xs font-mono tracking-wider text-brand-highlight">
                            {(movie.similarity_score * 100).toFixed(0)}% match
                          </span>
                        </div>
                      </div>

                      {/* Movie info */}
                      <div className="flex-grow flex flex-col py-0.5">
                        
                        <h3 className={`font-serif text-2xl md:text-[1.7rem] tracking-tight text-brand-text-primary group-hover:text-white leading-snug mb-3 ${HOVER_TRANSITION}`}>
                          {movie.title}
                        </h3>

                        {movie.match_reason && (
                          <div className={`mb-4 font-serif italic text-brand-text-secondary group-hover:text-brand-text-primary/90 leading-relaxed text-base border-l-2 border-brand-highlight/40 group-hover:border-brand-highlight/70 pl-4 py-0.5 ${HOVER_TRANSITION}`}>
                            {movie.match_reason}
                          </div>
                        )}

                        <p className="text-brand-text-secondary text-base leading-[1.8] line-clamp-3 mb-5">
                          {movie.overview}
                        </p>

                        <div className="mt-auto space-y-4">
                          {/* Genres */}
                          <div className="flex flex-wrap gap-2">
                            {movie.genres.slice(0, 4).map((genre) => (
                              <span
                                key={genre}
                                className={`text-xs text-brand-text-secondary/70 group-hover:text-brand-text-secondary border border-brand-divider/50 px-3 py-1.5 rounded-full tracking-wide uppercase ${HOVER_TRANSITION}`}
                              >
                                {genre}
                              </span>
                            ))}
                          </div>
                          
                          {/* Metadata row — separators between items */}
                          <div className="text-xs text-brand-text-secondary/70 font-mono tracking-widest uppercase flex flex-wrap items-center gap-x-3 gap-y-1">
                            {movie.runtime && <span>{movie.runtime} min</span>}
                            {movie.runtime && <span className="text-brand-divider">·</span>}
                            <span>{movie.release_year}</span>
                            <span className="text-brand-divider">·</span>
                            <span>{movie.rating?.toFixed(1)}/10</span>
                          </div>

                          {/* Action Buttons */}
                          <div className={`flex items-center gap-6 pt-3.5 border-t border-brand-divider/20 opacity-50 group-hover:opacity-100 ${HOVER_TRANSITION}`}>
                            <button
                              onClick={(e) => toggleWatchlist(e, movie)}
                              className="flex items-center gap-2 text-xs uppercase tracking-[0.12em] font-mono text-brand-text-secondary hover:text-brand-accent transition-colors duration-250 focus:outline-none"
                            >
                              <svg className="w-4 h-4" fill={state.watchlist.some(m => m.id === movie.id) ? "currentColor" : "none"} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z" />
                              </svg>
                              {state.watchlist.some(m => m.id === movie.id) ? "Saved" : "Watchlist"}
                            </button>
                            <button
                              onClick={(e) => handleFindSimilar(e, movie)}
                              className="flex items-center gap-2 text-xs uppercase tracking-[0.12em] font-mono text-brand-text-secondary hover:text-brand-accent transition-colors duration-250 focus:outline-none"
                            >
                              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
                              </svg>
                              Find Similar
                            </button>
                          </div>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        {/* ─── FOOTER ─────────────────────────────────────── */}
        <footer className="w-full border-t border-brand-divider/30 mt-auto">
          <div className="max-w-7xl mx-auto px-8 md:px-12 py-14">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-12 lg:gap-10 mb-12">
              
              {/* Col 1: Brand */}
              <div>
                <span className="font-serif text-xl tracking-[0.1em] text-brand-text-primary font-medium block mb-4">CineMate</span>
                <p className="text-[15px] text-brand-text-secondary leading-relaxed mb-5 max-w-xs">
                  Discover films through feelings, not filters. A semantic search engine built for movie lovers.
                </p>
                <div className="flex items-center gap-4">
                  <a href="https://github.com" target="_blank" rel="noopener noreferrer" className={`text-brand-text-secondary/60 hover:text-brand-text-primary ${HOVER_TRANSITION}`}>
                    <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12Z"/></svg>
                  </a>
                  <a href="#" className={`text-[15px] text-brand-text-secondary/60 hover:text-brand-text-primary ${HOVER_TRANSITION}`}>About</a>
                </div>
              </div>

              {/* Col 2: Explore */}
              <div>
                <span className="text-xs tracking-[0.2em] uppercase text-brand-text-secondary/60 font-mono block mb-5">Explore</span>
                <ul className="space-y-3">
                  {['Trending'].map(item => (
                    <li key={item}><span className={`text-[15px] text-brand-text-secondary hover:text-brand-text-primary cursor-pointer ${HOVER_TRANSITION}`}>{item}</span></li>
                  ))}
                </ul>
              </div>

              {/* Col 3: Resources */}
              <div>
                <span className="text-xs tracking-[0.2em] uppercase text-brand-text-secondary/60 font-mono block mb-5">Resources</span>
                <ul className="space-y-3">
                  {['Roadmap', 'API', 'Feedback', 'Changelog'].map(item => (
                    <li key={item}><span className={`text-[15px] text-brand-text-secondary hover:text-brand-text-primary cursor-pointer ${HOVER_TRANSITION}`}>{item}</span></li>
                  ))}
                </ul>
              </div>

              {/* Col 4: Stay Updated */}
              <div>
                <span className="text-xs tracking-[0.2em] uppercase text-brand-text-secondary/60 font-mono block mb-5">Stay Updated</span>
                <div className="flex gap-2 mb-5">
                  <input 
                    type="email" 
                    placeholder="your@email.com" 
                    className="flex-1 bg-brand-surface/50 border border-brand-divider rounded-xl px-4 py-2.5 text-[15px] text-brand-text-primary placeholder-brand-text-secondary/40 outline-none focus:border-brand-highlight/40 transition-colors duration-250"
                  />
                  <button className={`px-3.5 py-2.5 bg-brand-surface border border-brand-divider rounded-xl text-brand-text-secondary hover:text-brand-text-primary hover:border-brand-highlight/40 ${HOVER_TRANSITION}`}>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                    </svg>
                  </button>
                </div>
                <div className="flex gap-4">
                  {['Twitter', 'Discord'].map(social => (
                    <span key={social} className={`text-[15px] text-brand-text-secondary/60 hover:text-brand-text-primary cursor-pointer ${HOVER_TRANSITION}`}>{social}</span>
                  ))}
                </div>
              </div>
            </div>

            {/* Bottom row */}
            <div className="pt-6 border-t border-brand-divider/20 flex flex-col md:flex-row justify-between items-center gap-4 text-[11px] uppercase tracking-[0.18em] font-mono text-brand-text-secondary/40">
              <div className="flex items-center gap-6">
                <span>Privacy</span>
                <span>Terms</span>
                <span>TMDB Attribution</span>
              </div>
              <div>v0.1.0</div>
            </div>
          </div>
        </footer>
      </main>

      {/* ─── MOVIE DETAIL OVERLAY ─────────────────────────── */}
      {state.ui.detailOpen && state.selectedMovie && (
        <div 
          className="fixed inset-0 z-[60] overflow-y-auto bg-brand-bg/95 backdrop-blur-xl flex justify-center py-14 md:py-20 px-6 md:px-12"
          role="dialog"
          aria-modal="true"
        >
          <div className="relative w-full max-w-6xl bg-transparent flex flex-col md:flex-row gap-10 md:gap-14" style={{ animation: 'fade-in 0.3s ease-out both' }}>
            
            {/* Immersive backdrop */}
            {state.selectedMovie.poster_url && (
              <div 
                className="absolute inset-0 z-[-1] opacity-5 blur-[100px] pointer-events-none bg-cover bg-center" 
                style={{ backgroundImage: `url(${state.selectedMovie.poster_url})`}} 
              />
            )}

            <button
              onClick={() => handleMovieSelect(null)}
              className="absolute -top-4 right-0 text-brand-text-secondary hover:text-brand-text-primary transition-colors duration-250 focus:outline-none rounded-xl p-2 hover:bg-brand-surface/50"
              aria-label="Close detail view"
            >
              <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <div className="w-full md:w-[28%] shrink-0">
              {state.selectedMovie.poster_url ? (
                <img
                  src={state.selectedMovie.poster_url}
                  alt={state.selectedMovie.title}
                  className="w-full h-auto object-cover border border-brand-divider/40 shadow-2xl rounded-2xl"
                />
              ) : (
                <div className="w-full aspect-[2/3] bg-brand-surface flex items-center justify-center text-sm tracking-widest text-brand-text-secondary/50 uppercase rounded-2xl">
                  No Poster
                </div>
              )}
            </div>

            <div className="flex-grow flex flex-col">
              <h2 className="font-serif text-4xl md:text-5xl tracking-tight text-brand-text-primary mb-5 leading-[1.1]">
                {state.selectedMovie.title}
              </h2>

              {state.selectedMovie.match_reason && (
                <div className="mb-7 font-serif italic text-brand-text-secondary text-lg md:text-xl border-l-2 border-brand-highlight/50 pl-5">
                  {state.selectedMovie.match_reason}
                </div>
              )}

              <p className="text-brand-text-secondary text-base md:text-lg leading-[1.9] mb-10">
                {state.selectedMovie.overview}
              </p>
              
              <div className="grid grid-cols-2 gap-x-8 gap-y-6 text-base mb-12 border-t border-brand-divider/30 pt-7">
                {[
                  { label: 'Director', value: 'Unknown' },
                  { label: 'Cast', value: 'Unknown' },
                  { label: 'Runtime', value: state.selectedMovie.runtime ? `${state.selectedMovie.runtime} minutes` : 'N/A' },
                  { label: 'Genres', value: state.selectedMovie.genres.join(', ') || 'N/A' },
                  { label: 'Studios', value: state.selectedMovie.production_companies?.join(', ') || 'N/A' },
                  { label: 'Languages', value: state.selectedMovie.spoken_languages?.join(', ') || 'N/A' },
                ].map(item => (
                  <div key={item.label}>
                    <span className="text-xs uppercase font-mono tracking-[0.18em] text-brand-text-secondary/60 block mb-1.5">{item.label}</span>
                    <p className="text-brand-text-secondary tracking-wide">{item.value}</p>
                  </div>
                ))}
              </div>

              <button
                onClick={() => {
                  const q = state.selectedMovie.keywords?.slice(0, 4).join(', ') || state.selectedMovie.title;
                  handleMovieSelect(null);
                  handleSuggestionClick(`Something matching the themes of ${q}`);
                }}
                className={`w-full md:w-fit py-3.5 px-10 bg-brand-surface/50 border border-brand-divider hover:border-brand-highlight/50 text-brand-text-secondary hover:text-brand-text-primary font-sans text-xs tracking-[0.18em] uppercase rounded-xl mt-auto focus:outline-none ${HOVER_TRANSITION}`}
              >
                Explore Similar Feelings
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── SPOTIFY SYNC OVERLAY ─────────────────────────── */}
      {state.ui.spotifyOpen && (
        <div 
          className="fixed inset-0 z-[60] overflow-y-auto bg-brand-bg/95 backdrop-blur-xl flex items-center justify-center py-14 px-6"
          role="dialog"
          aria-modal="true"
        >
          <div className="relative w-full max-w-2xl bg-brand-surface/40 border border-brand-divider p-10 md:p-14 rounded-3xl text-center shadow-2xl" style={{ animation: 'fade-in-up 0.4s ease-out both' }}>
            <button
              onClick={() => updateState({ ui: { spotifyOpen: false } })}
              className="absolute top-6 right-6 text-brand-text-secondary hover:text-brand-text-primary transition-colors duration-250 focus:outline-none rounded-xl p-2 hover:bg-brand-surface/50"
              aria-label="Close Spotify sync view"
            >
              <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>

            <svg className="w-16 h-16 mx-auto text-[#1DB954] mb-6" fill="currentColor" viewBox="0 0 24 24"><path d="M12 0C5.4 0 0 5.4 0 12s5.4 12 12 12 12-5.4 12-12S18.66 0 12 0zm5.521 17.34c-.24.359-.66.48-1.021.24-2.82-1.74-6.36-2.101-10.561-1.141-.418.122-.779-.179-.899-.539-.12-.421.18-.78.54-.9 4.56-1.021 8.52-.6 11.64 1.32.42.18.54.659.301 1.02zm1.44-3.3c-.301.42-.84.6-1.262.3-3.239-1.98-8.159-2.58-11.939-1.38-.479.12-1.02-.12-1.14-.6-.12-.48.12-1.021.6-1.141C9.6 9.9 15 10.561 18.72 12.84c.361.181.54.84.241 1.2zm.12-3.36C15.24 8.4 8.82 8.16 5.16 9.301c-.6.179-1.2-.181-1.38-.721-.18-.6.18-1.2.72-1.38 4.26-1.26 11.28-1.02 15.721 1.621.539.3.719 1.02.419 1.56-.239.54-.959.72-1.56.3z"/></svg>

            <h2 className="font-serif text-3xl md:text-4xl text-brand-text-primary mb-4 leading-tight">
              Synesthetic Discovery
            </h2>
            <p className="text-brand-text-secondary text-base leading-relaxed mb-10 max-w-lg mx-auto">
              Paste a Spotify playlist link. We'll analyze its audio features (valence, energy, acousticness) and map it to a cinematic mood query to find movies that feel like your music.
            </p>

            <div className="flex flex-col gap-4 max-w-md mx-auto">
              <input
                type="text"
                placeholder="https://open.spotify.com/playlist/..."
                value={state.spotifyUrl}
                onChange={(e) => updateState({ spotifyUrl: e.target.value })}
                className="w-full bg-brand-surface/80 border border-brand-divider rounded-xl px-5 py-4 text-brand-text-primary placeholder-brand-text-secondary/40 outline-none focus:border-[#1DB954]/50 transition-colors duration-250 text-center"
              />
              <button
                onClick={handleSpotifySync}
                disabled={state.spotifyLoading || !state.spotifyUrl.includes('spotify.com/playlist')}
                className="w-full py-4 bg-[#1DB954] hover:bg-[#1ed760] disabled:bg-brand-surface disabled:text-brand-text-secondary disabled:cursor-not-allowed text-brand-bg font-sans font-medium tracking-[0.15em] uppercase rounded-xl transition-colors duration-250 flex items-center justify-center gap-2"
              >
                {state.spotifyLoading ? (
                  <>
                    <svg className="animate-spin h-5 w-5 text-brand-bg" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                    Analyzing...
                  </>
                ) : (
                  "Find Matches"
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

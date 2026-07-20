"use client";

import { useEffect, useState, useMemo, useCallback } from 'react';
import { apiClient, EntityConflict } from '@/lib/api';
import { ShieldAlert, Check, X, User, Search, Filter, ArrowLeft, ArrowRight, GitMerge, FileText } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

const ITEMS_PER_PAGE = 3;

export default function EntityConflictsPage() {
  const [conflicts, setConflicts] = useState<EntityConflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);

  // Filters & Pagination
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("pending");
  const [similarityThreshold, setSimilarityThreshold] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [focusedIndex, setFocusedIndex] = useState<number>(0);

  useEffect(() => {
    async function loadConflicts() {
      try {
        const data = await apiClient.getConflicts();
        setConflicts(data);
      } catch (e) {
        console.error("Failed to load conflicts", e);
      } finally {
        setLoading(false);
      }
    }
    loadConflicts();
  }, []);

  // Derived state
  const filteredConflicts = useMemo(() => {
    return conflicts.filter((c) => {
      const matchesSearch = c.name_a.toLowerCase().includes(searchQuery.toLowerCase()) || 
                            c.name_b.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus = statusFilter === 'all' || c.status === statusFilter;
      const matchesSimilarity = (c.similarity * 100) >= similarityThreshold;
      return matchesSearch && matchesStatus && matchesSimilarity;
    });
  }, [conflicts, searchQuery, statusFilter, similarityThreshold]);

  const totalPages = Math.ceil(filteredConflicts.length / ITEMS_PER_PAGE) || 1;

  const paginatedConflicts = useMemo(() => {
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    return filteredConflicts.slice(startIndex, startIndex + ITEMS_PER_PAGE);
  }, [filteredConflicts, currentPage]);

  const handleApprove = useCallback(async (id: string) => {
    setProcessingId(id);
    try {
      await apiClient.approveConflict(id);
      setConflicts((prev) => prev.map(c => c.id === id ? { ...c, status: 'approved' } : c));
    } catch (e) {
      console.error(e);
    } finally {
      setProcessingId(null);
    }
  }, []);

  const handleReject = useCallback(async (id: string) => {
    setProcessingId(id);
    try {
      await apiClient.rejectConflict(id);
      setConflicts((prev) => prev.map(c => c.id === id ? { ...c, status: 'rejected' } : c));
    } catch (e) {
      console.error(e);
    } finally {
      setProcessingId(null);
    }
  }, []);

  const handleFilterChange = <T,>(setter: React.Dispatch<React.SetStateAction<T>>, value: T) => {
    setter(value);
    setCurrentPage(1);
    setFocusedIndex(0);
  };

  // Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if user is typing in an input field
      const activeTag = document.activeElement?.tagName;
      if (activeTag === 'INPUT' || activeTag === 'TEXTAREA' || activeTag === 'SELECT' || (document.activeElement as HTMLElement)?.isContentEditable) {
        return;
      }

      const key = e.key.toLowerCase();

      if (['arrowdown', 'arrowup', 'a', 'r', 'arrowright', 'arrowleft'].includes(key)) {
        // Prevent default browser behavior (e.g., scrolling with arrows/space) if it's one of our shortcuts
        e.preventDefault();
      }

      if (key === 'arrowdown') {
        setFocusedIndex(prev => Math.min(prev + 1, Math.max(0, paginatedConflicts.length - 1)));
      } else if (key === 'arrowup') {
        setFocusedIndex(prev => Math.max(prev - 1, 0));
      } else if (key === 'a') {
        const target = paginatedConflicts[focusedIndex];
        if (target && target.status === 'pending' && !processingId) handleApprove(target.id);
      } else if (key === 'r') {
        const target = paginatedConflicts[focusedIndex];
        if (target && target.status === 'pending' && !processingId) handleReject(target.id);
      } else if (key === 'arrowright') {
        setCurrentPage(prev => Math.min(prev + 1, totalPages));
        setFocusedIndex(0);
      } else if (key === 'arrowleft') {
        setCurrentPage(prev => Math.max(prev - 1, 1));
        setFocusedIndex(0);
      }
    };

    window.addEventListener('keydown', handleKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', handleKeyDown, { capture: true });
  }, [paginatedConflicts, focusedIndex, processingId, handleApprove, handleReject, totalPages]);

  // Auto-scroll to focused item
  useEffect(() => {
    if (paginatedConflicts.length > 0) {
      const el = document.getElementById(`conflict-card-${focusedIndex}`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [focusedIndex, paginatedConflicts]);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <div className="text-muted-foreground text-sm tracking-widest uppercase font-medium animate-in fade-in duration-500">
          Initializing neural matrix...
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 md:p-10 max-w-6xl mx-auto pb-32 relative min-h-screen flex flex-col">
      {/* Header */}
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-6"
      >
        <div className="flex items-center gap-4">
          <div className="bg-card-bg p-2.5 rounded-xl border border-glass-border shadow-[0_0_20px_var(--color-accent-glow)] relative group">
            <div className="absolute inset-0 bg-accent/20 blur-xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
            <ShieldAlert className="w-6 h-6 text-accent relative z-10" />
          </div>
          <div>
            <h1 className="text-3xl font-light text-foreground tracking-tight">Entity Conflicts</h1>
            <p className="text-sm text-muted-foreground mt-1 font-light">
              Review and resolve potential duplicate entities.
            </p>
          </div>
        </div>
        
        {/* Shortcut Legend */}
        <div className="hidden md:flex items-center gap-4 text-xs text-muted-foreground bg-card-bg/50 px-4 py-2 rounded-lg border border-glass-border">
          <span className="flex items-center gap-1"><kbd className="bg-background px-1.5 py-0.5 rounded border border-glass-border font-mono font-medium text-foreground">↑/↓</kbd> Nav</span>
          <span className="flex items-center gap-1"><kbd className="bg-background px-1.5 py-0.5 rounded border border-glass-border font-mono font-medium text-foreground">a</kbd> Approve</span>
          <span className="flex items-center gap-1"><kbd className="bg-background px-1.5 py-0.5 rounded border border-glass-border font-mono font-medium text-foreground">r</kbd> Reject</span>
        </div>
      </motion.div>

      {/* Toolbar / Filters */}
      <motion.div 
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="sticky top-6 z-30 mb-8 flex flex-col sm:flex-row gap-4 p-4 glass-panel rounded-xl shadow-lg border border-glass-border backdrop-blur-md bg-card-bg/80"
      >
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input 
            type="text" 
            placeholder="Search entities..." 
            value={searchQuery}
            onChange={(e) => handleFilterChange(setSearchQuery, e.target.value)}
            className="w-full bg-background/50 border border-glass-border rounded-lg pl-10 pr-4 py-2 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-accent transition-shadow placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex gap-4">
          <div className="flex items-center gap-2 bg-background/50 border border-glass-border rounded-lg px-3">
            <Filter className="w-4 h-4 text-muted-foreground" />
            <select 
              value={statusFilter}
              onChange={(e) => handleFilterChange(setStatusFilter, e.target.value)}
              className="bg-transparent text-sm text-foreground focus:outline-none py-2 appearance-none cursor-pointer"
            >
              <option value="all" className="bg-background text-foreground">All Statuses</option>
              <option value="pending" className="bg-background text-foreground">Pending</option>
              <option value="approved" className="bg-background text-foreground">Approved</option>
              <option value="rejected" className="bg-background text-foreground">Rejected</option>
            </select>
          </div>
          <div className="flex items-center gap-3 bg-background/50 border border-glass-border rounded-lg px-4 py-2">
            <span className="text-xs text-muted-foreground font-medium uppercase tracking-wider">Sim &gt;</span>
            <input 
              type="range" 
              min="0" max="100" 
              value={similarityThreshold}
              onChange={(e) => handleFilterChange(setSimilarityThreshold, Number(e.target.value))}
              className="w-24 accent-accent"
            />
            <span className="text-xs text-foreground min-w-[2ch]">{similarityThreshold}%</span>
          </div>
        </div>
      </motion.div>

      {/* Main Queue */}
      {paginatedConflicts.length === 0 ? (
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass-panel rounded-2xl p-16 text-center relative overflow-hidden flex-1 flex flex-col items-center justify-center"
        >
          <div className="absolute inset-0 bg-gradient-to-b from-accent/5 to-transparent" />
          <Check className="w-12 h-12 text-accent/50 mx-auto mb-6 drop-shadow-[0_0_15px_var(--color-accent-glow)]" />
          <h3 className="text-xl font-medium text-foreground tracking-wide">Queue Empty</h3>
          <p className="text-muted-foreground mt-2 font-light">No conflicts match your current filters.</p>
        </motion.div>
      ) : (
        <div className="space-y-6 flex-1">
          <AnimatePresence mode="popLayout">
            {paginatedConflicts.map((conflict, idx) => {
              const isFocused = idx === focusedIndex;
              const isProcessing = processingId === conflict.id;

              return (
                <motion.div
                  key={conflict.id}
                  id={`conflict-card-${idx}`}
                  layout
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, filter: "blur(5px)" }}
                  transition={{ duration: 0.3 }}
                  className={`glass-panel rounded-2xl overflow-hidden relative group transition-all duration-300 ${
                    isFocused ? 'ring-2 ring-accent/50 shadow-[0_0_30px_var(--color-accent-glow)] opacity-100' : 'opacity-40 hover:opacity-60'
                  } ${isProcessing ? 'opacity-20 pointer-events-none' : ''}`}
                  onClick={() => setFocusedIndex(idx)}
                >
                  {/* Subtle gradient hover effect */}
                  <div className={`absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent transition-opacity duration-500 ${isFocused ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`} />
                  
                  {/* Header */}
                  <div className="flex items-center justify-between p-5 border-b border-glass-border bg-card-bg">
                    <div className="flex items-center gap-3">
                      <span className="px-3 py-1 text-[10px] font-bold tracking-widest rounded bg-primary/5 text-foreground border border-glass-border">
                        {conflict.type_a}
                      </span>
                      <span className="text-xs text-muted-foreground uppercase tracking-wider">
                        Detected {new Date(conflict.created_at).toLocaleDateString('en-US', { timeZone: 'UTC', year: 'numeric', month: 'short', day: 'numeric' })}
                      </span>
                      {conflict.status !== 'pending' && (
                        <span className={`px-2 py-0.5 text-[10px] font-bold tracking-widest rounded uppercase ${conflict.status === 'approved' ? 'bg-green-500/10 text-green-500 border border-green-500/20' : 'bg-red-500/10 text-red-500 border border-red-500/20'}`}>
                          {conflict.status}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 bg-background/50 px-4 py-1.5 rounded-full border border-glass-border shadow-[inset_0_1px_0_0_var(--color-glass-highlight)]">
                      <span className="text-[10px] text-muted-foreground uppercase tracking-widest">Similarity</span>
                      <span className="text-sm font-medium text-accent text-glow-accent">
                        {Math.round(conflict.similarity * 100)}%
                      </span>
                    </div>
                  </div>

                  {/* Body - Diff Viewer */}
                  <div className="p-6 relative bg-card-bg/50">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8 relative z-10">
                      {/* Visual Separator for Desktop */}
                      <div className="hidden md:block absolute left-1/2 top-4 bottom-4 w-px bg-gradient-to-b from-transparent via-glass-border to-transparent -translate-x-1/2" />
                      
                      {/* Entity A */}
                      <div className="space-y-4">
                        <div className="flex items-center gap-3">
                          <div className="bg-primary/5 p-2 rounded border border-glass-border">
                            <User className="w-4 h-4 text-muted-foreground" />
                          </div>
                          <h3 className="text-xl font-light text-foreground tracking-tight line-through decoration-red-500/50 decoration-2">{conflict.name_a}</h3>
                        </div>
                        <div className="bg-background/40 p-4 rounded-xl border border-glass-border relative overflow-hidden group/quote">
                          <div className="absolute top-0 left-0 w-1 h-full bg-red-500/30" />
                          <div className="flex items-center gap-2 mb-2">
                            <FileText className="w-3 h-3 text-muted-foreground" />
                            <span className="text-[9px] uppercase tracking-widest text-muted-foreground font-medium">Evidence A</span>
                          </div>
                          <p className="text-sm text-foreground/80 leading-relaxed font-light italic">&quot;{conflict.quote_a}&quot;</p>
                        </div>
                      </div>

                      {/* Entity B */}
                      <div className="space-y-4">
                        <div className="flex items-center gap-3">
                          <div className="bg-primary/5 p-2 rounded border border-glass-border">
                            <User className="w-4 h-4 text-muted-foreground" />
                          </div>
                          <h3 className="text-xl font-light text-foreground tracking-tight text-green-500/90">{conflict.name_b}</h3>
                        </div>
                        <div className="bg-background/40 p-4 rounded-xl border border-glass-border relative overflow-hidden group/quote">
                          <div className="absolute top-0 left-0 w-1 h-full bg-green-500/30" />
                          <div className="flex items-center gap-2 mb-2">
                            <FileText className="w-3 h-3 text-muted-foreground" />
                            <span className="text-[9px] uppercase tracking-widest text-muted-foreground font-medium">Evidence B</span>
                          </div>
                          <p className="text-sm text-foreground/80 leading-relaxed font-light italic">&quot;{conflict.quote_b}&quot;</p>
                        </div>
                      </div>
                    </div>

                    {/* Merge Preview */}
                    <div className="mt-8 pt-6 border-t border-glass-border relative z-10">
                      <div className="flex items-center gap-2 mb-4">
                        <GitMerge className="w-4 h-4 text-accent" />
                        <h4 className="text-xs font-semibold uppercase tracking-widest text-foreground">Merge Preview</h4>
                      </div>
                      <div className="bg-accent/5 border border-accent/20 rounded-xl p-5 relative overflow-hidden">
                        <div className="absolute top-0 left-0 w-1 h-full bg-accent/50" />
                        <div className="flex items-center gap-3 mb-2">
                          <span className="px-2 py-0.5 text-[10px] font-bold tracking-widest rounded bg-accent/10 text-accent border border-accent/20">
                            {conflict.type_a}
                          </span>
                          <span className="text-lg font-medium text-foreground">{conflict.name_b}</span>
                          <span className="text-xs text-muted-foreground ml-2">(Canonical Name)</span>
                        </div>
                        <p className="text-sm text-muted-foreground font-light">
                          This action will alias <span className="text-foreground font-medium">{conflict.name_a}</span> to <span className="text-foreground font-medium">{conflict.name_b}</span>. Both pieces of evidence will be attributed to {conflict.name_b}.
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Footer / Actions */}
                  {conflict.status === 'pending' && (
                    <div className="p-5 border-t border-glass-border bg-card-bg flex justify-end gap-4 relative z-10">
                      <button
                        onClick={(e) => { e.stopPropagation(); handleReject(conflict.id); }}
                        disabled={!!processingId}
                        className="cinematic-button px-6 py-2.5 text-sm font-medium text-muted-foreground hover:text-foreground bg-transparent hover:bg-black/5 dark:hover:bg-white/5 border border-glass-border rounded-lg transition-colors flex items-center gap-2"
                      >
                        <X className="w-4 h-4" />
                        Reject
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); handleApprove(conflict.id); }}
                        disabled={!!processingId}
                        className="cinematic-button px-6 py-2.5 text-sm font-medium text-primary-foreground bg-primary hover:opacity-90 shadow-[0_0_20px_var(--color-glass-highlight)] rounded-lg transition-all flex items-center gap-2"
                      >
                        <Check className="w-4 h-4" />
                        Approve Merge
                      </button>
                    </div>
                  )}
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}

      {/* Pagination Footer */}
      {totalPages > 1 && (
        <div className="mt-10 flex items-center justify-between border-t border-glass-border pt-6">
          <p className="text-sm text-muted-foreground font-light">
            Showing <span className="text-foreground font-medium">{paginatedConflicts.length}</span> of <span className="text-foreground font-medium">{filteredConflicts.length}</span> results
          </p>
          <div className="flex items-center gap-2">
            <button 
              onClick={() => { setCurrentPage(p => Math.max(1, p - 1)); setFocusedIndex(0); }}
              disabled={currentPage === 1}
              className="p-2 rounded-lg border border-glass-border hover:bg-background/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-muted-foreground"
            >
              <ArrowLeft className="w-4 h-4" />
            </button>
            <div className="flex items-center gap-1 px-4">
              {Array.from({ length: totalPages }).map((_, i) => (
                <div 
                  key={i} 
                  className={`w-2 h-2 rounded-full transition-colors ${i + 1 === currentPage ? 'bg-accent shadow-[0_0_8px_var(--color-accent-glow)]' : 'bg-glass-border'}`}
                />
              ))}
            </div>
            <button 
              onClick={() => { setCurrentPage(p => Math.min(totalPages, p + 1)); setFocusedIndex(0); }}
              disabled={currentPage === totalPages}
              className="p-2 rounded-lg border border-glass-border hover:bg-background/50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-muted-foreground"
            >
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

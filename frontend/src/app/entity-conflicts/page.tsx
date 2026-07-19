"use client";

import { useEffect, useState } from 'react';
import { apiClient, EntityConflict } from '@/lib/api';
import { ShieldAlert, Check, X, User } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function EntityConflictsPage() {
  const [conflicts, setConflicts] = useState<EntityConflict[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);

  useEffect(() => {
    async function loadConflicts() {
      try {
        const data = await apiClient.getPendingConflicts();
        setConflicts(data);
      } catch (e) {
        console.error("Failed to load conflicts", e);
      } finally {
        setLoading(false);
      }
    }
    loadConflicts();
  }, []);

  const handleApprove = async (id: string) => {
    setProcessingId(id);
    try {
      await apiClient.approveConflict(id);
      setConflicts((prev) => prev.filter((c) => c.id !== id));
    } catch (e) {
      console.error(e);
    } finally {
      setProcessingId(null);
    }
  };

  const handleReject = async (id: string) => {
    setProcessingId(id);
    try {
      await apiClient.rejectConflict(id);
      setConflicts((prev) => prev.filter((c) => c.id !== id));
    } catch (e) {
      console.error(e);
    } finally {
      setProcessingId(null);
    }
  };

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center h-full">
        <motion.div 
          initial={{ opacity: 0 }} 
          animate={{ opacity: 1 }} 
          className="text-muted-foreground text-sm tracking-widest uppercase font-medium"
        >
          Initializing neural matrix...
        </motion.div>
      </div>
    );
  }

  return (
    <div className="p-10 max-w-6xl mx-auto">
      <motion.div 
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-10 flex items-center gap-4 border-b border-glass-border pb-6"
      >
        <div className="bg-card-bg p-2.5 rounded-xl border border-glass-border shadow-[0_0_20px_var(--color-accent-glow)] relative group">
          <div className="absolute inset-0 bg-accent/20 blur-xl rounded-full opacity-0 group-hover:opacity-100 transition-opacity" />
          <ShieldAlert className="w-6 h-6 text-accent relative z-10" />
        </div>
        <div>
          <h1 className="text-3xl font-light text-foreground tracking-tight">Entity Conflicts</h1>
          <p className="text-sm text-muted-foreground mt-1 font-light">
            Review and resolve potential duplicate entities detected across the workspace memory graph.
          </p>
        </div>
      </motion.div>

      {conflicts.length === 0 ? (
        <motion.div 
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="glass-panel rounded-2xl p-16 text-center relative overflow-hidden"
        >
          <div className="absolute inset-0 bg-gradient-to-b from-accent/5 to-transparent" />
          <Check className="w-12 h-12 text-accent/50 mx-auto mb-6 drop-shadow-[0_0_15px_var(--color-accent-glow)]" />
          <h3 className="text-xl font-medium text-foreground tracking-wide">System optimal</h3>
          <p className="text-muted-foreground mt-2 font-light">No pending entity conflicts require review.</p>
        </motion.div>
      ) : (
        <div className="space-y-8">
          <AnimatePresence>
            {conflicts.map((conflict) => (
              <motion.div
                key={conflict.id}
                layout
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, filter: "blur(10px)" }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                className={`glass-panel rounded-2xl overflow-hidden relative group ${
                  processingId === conflict.id ? 'opacity-50 pointer-events-none' : ''
                }`}
              >
                {/* Subtle gradient hover effect */}
                <div className="absolute inset-0 bg-gradient-to-br from-primary/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
                
                {/* Header */}
                <div className="flex items-center justify-between p-6 border-b border-glass-border bg-card-bg">
                  <div className="flex items-center gap-3">
                    <span className="px-3 py-1 text-[10px] font-bold tracking-widest rounded bg-primary/5 text-foreground border border-glass-border">
                      {conflict.type_a}
                    </span>
                    <span className="text-xs text-muted-foreground uppercase tracking-wider">Detected {new Date(conflict.created_at).toLocaleDateString()}</span>
                  </div>
                  <div className="flex items-center gap-3 bg-background/50 px-4 py-1.5 rounded-full border border-glass-border shadow-[inset_0_1px_0_0_var(--color-glass-highlight)]">
                    <span className="text-[10px] text-muted-foreground uppercase tracking-widest">Similarity</span>
                    <span className="text-sm font-medium text-accent text-glow-accent">
                      {Math.round(conflict.similarity * 100)}%
                    </span>
                  </div>
                </div>

                {/* Body */}
                <div className="p-8 grid grid-cols-1 md:grid-cols-2 gap-12 relative bg-card-bg/50">
                  {/* Visual Separator for Desktop */}
                  <div className="hidden md:block absolute left-1/2 top-8 bottom-8 w-px bg-gradient-to-b from-transparent via-glass-border to-transparent -translate-x-1/2" />
                  
                  {/* Entity A */}
                  <div className="space-y-6 relative z-10">
                    <div className="flex items-center gap-4">
                      <div className="bg-primary/5 p-2.5 rounded-lg border border-glass-border">
                        <User className="w-5 h-5 text-muted-foreground" />
                      </div>
                      <h3 className="text-2xl font-light text-foreground tracking-tight">{conflict.name_a}</h3>
                    </div>
                    <div className="bg-background/40 p-5 rounded-xl border border-glass-border relative overflow-hidden group/quote hover:border-border-hover transition-colors">
                      <div className="absolute top-0 left-0 w-1 h-full bg-accent/20 group-hover/quote:bg-accent transition-colors" />
                      <div className="absolute -top-3 left-4 bg-background px-2 text-[9px] uppercase tracking-widest text-muted-foreground border border-glass-border rounded-full">Source context</div>
                      <p className="text-sm text-foreground/80 leading-relaxed font-light mt-2">&quot;{conflict.quote_a}&quot;</p>
                    </div>
                  </div>

                  {/* Entity B */}
                  <div className="space-y-6 relative z-10">
                    <div className="flex items-center gap-4">
                      <div className="bg-primary/5 p-2.5 rounded-lg border border-glass-border">
                        <User className="w-5 h-5 text-muted-foreground" />
                      </div>
                      <h3 className="text-2xl font-light text-foreground tracking-tight">{conflict.name_b}</h3>
                    </div>
                    <div className="bg-background/40 p-5 rounded-xl border border-glass-border relative overflow-hidden group/quote hover:border-border-hover transition-colors">
                      <div className="absolute top-0 left-0 w-1 h-full bg-purple-500/20 group-hover/quote:bg-purple-500 transition-colors" />
                      <div className="absolute -top-3 left-4 bg-background px-2 text-[9px] uppercase tracking-widest text-muted-foreground border border-glass-border rounded-full">Source context</div>
                      <p className="text-sm text-foreground/80 leading-relaxed font-light mt-2">&quot;{conflict.quote_b}&quot;</p>
                    </div>
                  </div>
                </div>

                {/* Footer / Actions */}
                <div className="p-6 border-t border-glass-border bg-card-bg flex justify-end gap-4 relative z-10">
                  <button
                    onClick={() => handleReject(conflict.id)}
                    disabled={!!processingId}
                    className="cinematic-button px-6 py-2.5 text-sm font-medium text-muted-foreground hover:text-foreground bg-transparent hover:bg-black/5 dark:hover:bg-white/5 border border-glass-border rounded-lg transition-colors flex items-center gap-2"
                  >
                    <X className="w-4 h-4" />
                    Reject
                  </button>
                  <button
                    onClick={() => handleApprove(conflict.id)}
                    disabled={!!processingId}
                    className="cinematic-button px-6 py-2.5 text-sm font-medium text-primary-foreground bg-primary hover:opacity-90 shadow-[0_0_20px_var(--color-glass-highlight)] rounded-lg transition-all flex items-center gap-2"
                  >
                    <Check className="w-4 h-4" />
                    Approve (Merge)
                  </button>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </div>
  );
}

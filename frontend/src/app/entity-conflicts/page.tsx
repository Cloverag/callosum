"use client";

import { useEffect, useState } from 'react';
import { apiClient, EntityConflict } from '@/lib/api';
import { ShieldAlert, Check, X, User } from 'lucide-react';

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
      // Optimistic update
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
      // Optimistic update
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
        <div className="text-[#8691a7] text-lg animate-pulse">Loading conflicts...</div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-5xl mx-auto">
      <div className="mb-8 flex items-center gap-3 border-b border-[#273647] pb-6">
        <div className="bg-[#1E293B] p-2 rounded-lg border border-[#273647]">
          <ShieldAlert className="w-6 h-6 text-[#c0c1ff]" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-[#d4e4fa] tracking-tight">Entity Conflicts</h1>
          <p className="text-sm text-[#8691a7] mt-1">
            Review and resolve potential duplicate entities detected across the workspace.
          </p>
        </div>
      </div>

      {conflicts.length === 0 ? (
        <div className="bg-[#122131]/50 backdrop-blur-xl border border-[#273647] rounded-xl p-12 text-center">
          <Check className="w-12 h-12 text-[#bec6e0] mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium text-[#d4e4fa]">All clear</h3>
          <p className="text-[#8691a7] mt-2">No pending entity conflicts require review.</p>
        </div>
      ) : (
        <div className="space-y-6">
          {conflicts.map((conflict) => (
            <div
              key={conflict.id}
              className={`bg-[#1E293B]/60 backdrop-blur-[20px] border border-[#273647] rounded-xl overflow-hidden shadow-lg transition-all ${
                processingId === conflict.id ? 'opacity-50 scale-[0.99] pointer-events-none' : ''
              }`}
            >
              {/* Header */}
              <div className="flex items-center justify-between p-5 border-b border-[#273647]/50 bg-[#122131]/30">
                <div className="flex items-center gap-2">
                  <span className="px-2.5 py-1 text-[10px] font-bold tracking-wider rounded-full bg-[#3f465c] text-[#bec6e0]">
                    {conflict.type_a}
                  </span>
                  <span className="text-xs text-[#8691a7]">Detected {new Date(conflict.created_at).toLocaleDateString()}</span>
                </div>
                <div className="flex items-center gap-2 bg-[#051424] px-3 py-1 rounded-full border border-[#273647]">
                  <span className="text-xs text-[#8691a7]">Similarity</span>
                  <span className="text-sm font-semibold text-[#c0c1ff]">
                    {Math.round(conflict.similarity * 100)}%
                  </span>
                </div>
              </div>

              {/* Body */}
              <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-8 relative">
                {/* Visual Separator for Desktop */}
                <div className="hidden md:block absolute left-1/2 top-6 bottom-6 w-px bg-[#273647] -translate-x-1/2" />
                
                {/* Entity A */}
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <div className="bg-[#2c3a4c] p-2 rounded-lg">
                      <User className="w-5 h-5 text-[#bcc7de]" />
                    </div>
                    <h3 className="text-xl font-semibold text-[#d4e4fa]">{conflict.name_a}</h3>
                  </div>
                  <div className="bg-[#0d1c2d] p-4 rounded-lg border border-[#1c2b3c] relative">
                    <div className="absolute -top-3 left-4 bg-[#1E293B] px-2 text-[10px] uppercase tracking-wider text-[#8691a7]">Source context</div>
                    <p className="text-sm text-[#adb4ce] leading-relaxed italic">"{conflict.quote_a}"</p>
                  </div>
                </div>

                {/* Entity B */}
                <div className="space-y-4">
                  <div className="flex items-center gap-3">
                    <div className="bg-[#2c3a4c] p-2 rounded-lg">
                      <User className="w-5 h-5 text-[#bcc7de]" />
                    </div>
                    <h3 className="text-xl font-semibold text-[#d4e4fa]">{conflict.name_b}</h3>
                  </div>
                  <div className="bg-[#0d1c2d] p-4 rounded-lg border border-[#1c2b3c] relative">
                    <div className="absolute -top-3 left-4 bg-[#1E293B] px-2 text-[10px] uppercase tracking-wider text-[#8691a7]">Source context</div>
                    <p className="text-sm text-[#adb4ce] leading-relaxed italic">"{conflict.quote_b}"</p>
                  </div>
                </div>
              </div>

              {/* Footer / Actions */}
              <div className="p-5 border-t border-[#273647]/50 bg-[#122131]/30 flex justify-end gap-3">
                <button
                  onClick={() => handleReject(conflict.id)}
                  disabled={!!processingId}
                  className="px-5 py-2 text-sm font-medium text-[#d4e4fa] hover:text-white bg-transparent hover:bg-[#273647] border border-[#464554] rounded-lg transition-colors flex items-center gap-2"
                >
                  <X className="w-4 h-4" />
                  Reject (Keep Distinct)
                </button>
                <button
                  onClick={() => handleApprove(conflict.id)}
                  disabled={!!processingId}
                  className="px-5 py-2 text-sm font-medium text-white bg-[#6366f1] hover:bg-[#4f52c1] shadow-[0_0_15px_rgba(99,102,241,0.2)] rounded-lg transition-all flex items-center gap-2 border border-transparent shadow-[inset_0_1px_0_0_rgba(255,255,255,0.2)]"
                >
                  <Check className="w-4 h-4" />
                  Approve (Merge)
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

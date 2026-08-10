'use client';

import { Cpu } from 'lucide-react';

export type SalesAiResult = {
  mode?: string;
  applied?: boolean;
  recommendation?: { action?: string; rationale?: string; missing_fields?: string[] };
  scores?: {
    conversion_probability?: number;
    lead_temperature?: string;
    engagement_score?: number;
    urgency_level?: string;
    confidence_score?: number;
  };
  assigned_agent?: string | null;
  funnel_stage?: string | null;
  crm_sync?: unknown;
};

type Props = {
  result: SalesAiResult;
  isExecuting?: boolean;
  error?: string | null;
  onCancel: () => void;
  onConfirm: () => void;
};

export default function SalesAiModal({ result, isExecuting, error, onCancel, onConfirm }: Props) {
  const conf =
    result.scores?.conversion_probability ??
    result.scores?.confidence_score ??
    null;

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-[#13131a] border border-gray-800 rounded-2xl p-6 max-w-lg w-full shadow-2xl">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <Cpu className="w-5 h-5 text-indigo-400" />
          {result.applied ? 'Applied Next Best Action' : 'Preview Next Best Action'}
        </h3>

        <div className="space-y-4 mb-6">
          <div className="bg-[#0f0f13] p-4 rounded-xl border border-gray-800">
            <span className="text-xs text-gray-500 uppercase font-bold tracking-wider block mb-1">
              Recommended Action
            </span>
            <span className="text-indigo-400 font-semibold">
              {result.recommendation?.action || '—'}
            </span>
          </div>

          <div className="bg-[#0f0f13] p-4 rounded-xl border border-gray-800">
            <span className="text-xs text-gray-500 uppercase font-bold tracking-wider block mb-1">
              Rationale
            </span>
            <p className="text-sm text-gray-300">{result.recommendation?.rationale || '—'}</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-[#0f0f13] p-4 rounded-xl border border-gray-800">
              <span className="text-xs text-gray-500 uppercase font-bold tracking-wider block mb-1">
                Conversion
              </span>
              <span className="text-white font-bold">{conf != null ? `${conf}%` : '—'}</span>
            </div>
            <div className="bg-[#0f0f13] p-4 rounded-xl border border-gray-800">
              <span className="text-xs text-gray-500 uppercase font-bold tracking-wider block mb-1">
                Assigned To
              </span>
              <span className="text-white font-bold">{result.assigned_agent || 'Unassigned'}</span>
            </div>
            <div className="bg-[#0f0f13] p-4 rounded-xl border border-gray-800">
              <span className="text-xs text-gray-500 uppercase font-bold tracking-wider block mb-1">
                Funnel Stage
              </span>
              <span className="text-white font-bold">{result.funnel_stage || '—'}</span>
            </div>
            <div className="bg-[#0f0f13] p-4 rounded-xl border border-gray-800">
              <span className="text-xs text-gray-500 uppercase font-bold tracking-wider block mb-1">
                Temperature
              </span>
              <span className="text-white font-bold capitalize">
                {result.scores?.lead_temperature || '—'}
              </span>
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-400 bg-red-950/30 border border-red-900/40 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isExecuting}
            className="px-4 py-2 rounded-lg text-sm font-medium text-gray-400 hover:text-white hover:bg-gray-800 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isExecuting || result.applied === true}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
          >
            {isExecuting ? 'Applying…' : result.applied ? 'Applied' : 'Confirm & Apply'}
          </button>
        </div>
      </div>
    </div>
  );
}

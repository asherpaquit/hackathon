import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { Check, FileText, Brain, Table2, Download, Upload, Cpu, Clock } from 'lucide-react'

const STAGES = [
  { key: 'UPLOADED',           label: 'Upload',     Icon: Upload,   pct: 0   },
  { key: 'DOCLING_PROCESSING', label: 'PDF Parse',  Icon: Cpu,      pct: 10  },
  { key: 'EXTRACTING_TEXT',    label: 'Extracting', Icon: FileText, pct: 35  },
  { key: 'AI_PROCESSING',      label: 'AI Analysis',Icon: Brain,    pct: 70  },
  { key: 'WRITING_EXCEL',      label: 'Write Excel',Icon: Table2,   pct: 85  },
  { key: 'COMPLETE',           label: 'Complete',   Icon: Download, pct: 100 },
]

// Per-stage label shown under the elapsed timer
const STAGE_HINT = {
  DOCLING_PROCESSING: 'Parsing table structure…',
  EXTRACTING_TEXT:    'Reading sections & text…',
  AI_PROCESSING:      'Rule-based + AI extraction…',
  WRITING_EXCEL:      'Generating Excel output…',
  COMPLETE:           'Done!',
}

function stageIndex(status) {
  const idx = STAGES.findIndex(s => s.key === status)
  return idx === -1 ? 0 : idx
}

function formatTime(seconds) {
  if (!seconds || seconds <= 0) return '—'
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return s > 0 ? `${m}m ${s}s` : `${m}m`
}

export default function ProgressPanel({ job }) {
  const currentIdx  = stageIndex(job.status)
  const isError     = job.status === 'ERROR'
  const isComplete  = job.status === 'COMPLETE'
  const isActive    = !isError && !isComplete && job.status !== 'UPLOADED'

  // Tick every second while active to refresh elapsed display
  const [, setTick] = useState(0)
  useEffect(() => {
    if (!isActive) return
    const iv = setInterval(() => setTick(t => t + 1), 1000)
    return () => clearInterval(iv)
  }, [isActive])

  // Derive elapsed from job-level timestamps — accurate even when switching jobs
  const elapsed = job.started_at
    ? Math.floor(((job.ended_at || Date.now()) - job.started_at) / 1000)
    : 0
  const totalTime = job.started_at && job.ended_at
    ? Math.floor((job.ended_at - job.started_at) / 1000)
    : null

  // ETA estimation — only meaningful once we have enough data (pct > 8, elapsed > 15s)
  const pct = job.stage_pct || 0
  let eta = null
  if (isActive && pct > 8 && elapsed > 15 && pct < 98) {
    const estimatedTotal = (elapsed / pct) * 100
    eta = Math.max(0, estimatedTotal - elapsed)
  }

  return (
    <div className="card p-6 space-y-5">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-white truncate max-w-xs">{job.filename}</h3>
        <div className="flex items-center gap-3 flex-shrink-0">
          {isActive && (
            <div className="flex items-center gap-1 text-slate-400 text-xs">
              <Clock className="w-3 h-3" />
              <span className="font-mono">{formatTime(elapsed)}</span>
            </div>
          )}
          {isComplete && totalTime && (
            <div className="flex items-center gap-1 text-emerald-400 text-xs">
              <Clock className="w-3 h-3" />
              <span className="font-mono">{formatTime(totalTime)}</span>
            </div>
          )}
          <span className="text-sm font-mono text-slate-400 w-10 text-right">{pct}%</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="h-2 bg-[#0f172a] rounded-full overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${isError ? 'bg-red-500' : isComplete ? 'bg-emerald-500' : 'bg-amber-500'}`}
          animate={{ width: isError ? '100%' : `${pct}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
      </div>

      {/* ETA row */}
      {(isActive || isComplete) && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>{STAGE_HINT[job.status] || job.status?.replace(/_/g, ' ')}</span>
          {isActive && eta !== null && (
            <span className="font-mono text-amber-400">
              ~{formatTime(eta)} remaining
            </span>
          )}
          {isComplete && (
            <span className="text-emerald-400 font-medium">All done ✓</span>
          )}
        </div>
      )}

      {/* Stage stepper */}
      <div className="flex items-start gap-0">
        {STAGES.map((stage, idx) => {
          const done   = idx < currentIdx || isComplete
          const active = idx === currentIdx && !isError && !isComplete
          const { Icon } = stage

          return (
            <div key={stage.key} className="flex-1 flex flex-col items-center gap-2">
              <div className="flex items-center w-full">
                {idx > 0 && (
                  <div className={`flex-1 h-0.5 ${done || active ? 'bg-amber-500' : 'bg-[#334155]'}`} />
                )}
                <motion.div
                  className={`
                    w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0
                    border-2 transition-colors duration-300
                    ${done
                      ? 'bg-amber-500 border-amber-500'
                      : active
                        ? 'bg-[#0f172a] border-amber-400 pulse-amber'
                        : isError && idx === currentIdx
                          ? 'bg-red-500/20 border-red-500'
                          : 'bg-[#0f172a] border-[#334155]'
                    }
                  `}
                >
                  {done
                    ? <Check className="w-4 h-4 text-slate-900" />
                    : <Icon className={`w-4 h-4 ${active ? 'text-amber-400' : 'text-slate-600'}`} />
                  }
                </motion.div>
                {idx < STAGES.length - 1 && (
                  <div className={`flex-1 h-0.5 ${done ? 'bg-amber-500' : 'bg-[#334155]'}`} />
                )}
              </div>
              <span className={`text-xs text-center leading-tight ${
                active ? 'text-amber-400 font-medium' : done ? 'text-slate-300' : 'text-slate-600'
              }`}>
                {stage.label}
              </span>
            </div>
          )
        })}
      </div>

      {/* Live counters */}
      {!isError && (
        <div className="grid grid-cols-4 gap-2">
          <Stat label="Pages"     value={`${job.pages_done || 0} / ${job.pages_total || '—'}`} />
          <Stat label="Rows"      value={(job.rows_extracted || 0).toLocaleString()} />
          <Stat label="Engine"    value={job._docling ? 'Docling' : 'pdfplumber'} amber={!!job._docling} />
          <Stat
            label="Status"
            value={isComplete ? '✓ Done' : job.status?.replace(/_/g, ' ')}
            green={isComplete}
          />
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
          <p className="text-sm text-red-400">{job.error || 'An unknown error occurred'}</p>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, green, amber }) {
  return (
    <div className="bg-[#0f172a] rounded-lg p-3">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-sm font-mono font-medium truncate ${
        green ? 'text-emerald-400' : amber ? 'text-amber-400' : 'text-white'
      }`}>
        {value}
      </p>
    </div>
  )
}

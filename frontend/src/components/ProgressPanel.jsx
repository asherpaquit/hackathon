import { motion } from 'framer-motion'
import { Check, FileText, Brain, Table2, Download, Upload } from 'lucide-react'

const STAGES = [
  { key: 'UPLOADED',        label: 'Upload',      Icon: Upload,    pct: 10 },
  { key: 'EXTRACTING_TEXT', label: 'Extract Text', Icon: FileText,  pct: 30 },
  { key: 'AI_PROCESSING',   label: 'AI Analysis', Icon: Brain,     pct: 70 },
  { key: 'WRITING_EXCEL',   label: 'Write Excel', Icon: Table2,    pct: 85 },
  { key: 'COMPLETE',        label: 'Complete',    Icon: Download,  pct: 100 },
]

function stageIndex(status) {
  const idx = STAGES.findIndex(s => s.key === status)
  return idx === -1 ? 0 : idx
}

export default function ProgressPanel({ job }) {
  const currentIdx = stageIndex(job.status)
  const isError = job.status === 'ERROR'

  return (
    <div className="card p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-white">{job.filename}</h3>
        <span className="text-sm text-slate-400">{job.stage_pct || 0}%</span>
      </div>

      {/* Overall progress bar */}
      <div className="h-2 bg-[#0f172a] rounded-full overflow-hidden">
        <motion.div
          className={`h-full rounded-full ${isError ? 'bg-red-500' : 'bg-amber-500'}`}
          animate={{ width: isError ? '100%' : `${job.stage_pct || 0}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
      </div>

      {/* Stage stepper */}
      <div className="flex items-start gap-0">
        {STAGES.map((stage, idx) => {
          const done = idx < currentIdx || job.status === 'COMPLETE'
          const active = idx === currentIdx && !isError && job.status !== 'COMPLETE'
          const { Icon } = stage

          return (
            <div key={stage.key} className="flex-1 flex flex-col items-center gap-2">
              {/* Connector line before (except first) */}
              <div className="flex items-center w-full">
                {idx > 0 && (
                  <div className={`flex-1 h-0.5 ${done || active ? 'bg-amber-500' : 'bg-[#334155]'}`} />
                )}

                {/* Stage circle */}
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
                  {done ? (
                    <Check className="w-4 h-4 text-slate-900" />
                  ) : (
                    <Icon className={`w-4 h-4 ${active ? 'text-amber-400' : 'text-slate-600'}`} />
                  )}
                </motion.div>

                {idx < STAGES.length - 1 && (
                  <div className={`flex-1 h-0.5 ${done ? 'bg-amber-500' : 'bg-[#334155]'}`} />
                )}
              </div>

              {/* Label */}
              <span className={`text-xs text-center ${active ? 'text-amber-400 font-medium' : done ? 'text-slate-300' : 'text-slate-600'}`}>
                {stage.label}
              </span>
            </div>
          )
        })}
      </div>

      {/* Live counters */}
      {!isError && (
        <div className="grid grid-cols-3 gap-3">
          <Stat label="Pages" value={`${job.pages_done || 0} / ${job.pages_total || '—'}`} />
          <Stat label="Rows Found" value={(job.rows_extracted || 0).toLocaleString()} />
          <Stat
            label="Status"
            value={job.status === 'COMPLETE' ? '✓ Done' : job.status.replace('_', ' ')}
            green={job.status === 'COMPLETE'}
          />
        </div>
      )}

      {isError && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-3">
          <p className="text-sm text-red-400">{job.error || 'An unknown error occurred'}</p>
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, green }) {
  return (
    <div className="bg-[#0f172a] rounded-lg p-3">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-sm font-mono font-medium ${green ? 'text-emerald-400' : 'text-white'}`}>
        {value}
      </p>
    </div>
  )
}

import { motion, AnimatePresence } from 'framer-motion'
import { FileText, CheckCircle, XCircle, Loader2, Clock } from 'lucide-react'

const STATUS_CONFIG = {
  UPLOADED:       { label: 'Queued',     color: 'badge-slate',  Icon: Clock },
  EXTRACTING_TEXT:{ label: 'Extracting', color: 'badge-blue',   Icon: Loader2 },
  AI_PROCESSING:  { label: 'AI Parsing', color: 'badge-amber',  Icon: Loader2 },
  WRITING_EXCEL:  { label: 'Writing',    color: 'badge-blue',   Icon: Loader2 },
  COMPLETE:       { label: 'Ready',      color: 'badge-green',  Icon: CheckCircle },
  ERROR:          { label: 'Error',      color: 'badge-red',    Icon: XCircle },
}

function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.UPLOADED
  const { label, color, Icon } = cfg
  const spinning = ['EXTRACTING_TEXT', 'AI_PROCESSING', 'WRITING_EXCEL'].includes(status)

  return (
    <span className={color}>
      <Icon className={`w-3 h-3 mr-1 ${spinning ? 'animate-spin' : ''}`} />
      {label}
    </span>
  )
}

export default function FileQueue({ jobs, activeJobId, onSelect }) {
  return (
    <div className="card overflow-hidden">
      <div className="px-4 py-3 border-b border-[#334155] flex items-center justify-between">
        <h3 className="text-sm font-semibold text-white">Files</h3>
        <span className="badge badge-slate">{jobs.length}</span>
      </div>

      <div className="divide-y divide-[#334155] max-h-[60vh] overflow-y-auto">
        <AnimatePresence initial={false}>
          {jobs.map((job) => (
            <motion.button
              key={job.job_id}
              layout
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              onClick={() => onSelect(job)}
              className={`
                w-full text-left px-4 py-3 flex items-start gap-3
                transition-colors duration-150
                ${activeJobId === job.job_id
                  ? 'bg-amber-500/10 border-l-2 border-amber-500'
                  : 'hover:bg-[#334155]/30 border-l-2 border-transparent'
                }
              `}
            >
              <div className="w-8 h-8 bg-[#0f172a] rounded-lg flex items-center justify-center flex-shrink-0 mt-0.5">
                <FileText className="w-4 h-4 text-amber-400" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">{job.filename}</p>
                <div className="flex items-center gap-2 mt-1">
                  <StatusBadge status={job.status} />
                  {job.rows_extracted > 0 && (
                    <span className="text-xs text-slate-500">
                      {job.rows_extracted.toLocaleString()} rows
                    </span>
                  )}
                </div>

                {/* Mini progress bar */}
                {job.status !== 'UPLOADED' && job.status !== 'COMPLETE' && job.status !== 'ERROR' && (
                  <div className="mt-2 h-1 bg-[#0f172a] rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-amber-500 rounded-full"
                      animate={{ width: `${job.stage_pct || 0}%` }}
                      transition={{ duration: 0.5 }}
                    />
                  </div>
                )}

                {job.status === 'COMPLETE' && (
                  <div className="mt-2 h-1 bg-emerald-500/30 rounded-full overflow-hidden">
                    <div className="h-full w-full bg-emerald-500 rounded-full" />
                  </div>
                )}

                {job.status === 'ERROR' && job.error && (
                  <p className="text-xs text-red-400 mt-1 truncate">{job.error}</p>
                )}
              </div>
            </motion.button>
          ))}
        </AnimatePresence>
      </div>
    </div>
  )
}

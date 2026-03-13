import { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import { Upload, FileText } from 'lucide-react'

export default function DropZone({ onFilesAccepted, compact = false }) {
  const onDrop = useCallback(
    (accepted) => {
      if (accepted.length > 0) onFilesAccepted(accepted)
    },
    [onFilesAccepted]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    multiple: true,
  })

  return (
    <motion.div
      {...getRootProps()}
      layout
      className={`
        relative cursor-pointer rounded-2xl border-2 border-dashed transition-all duration-300
        ${isDragActive
          ? 'border-amber-400 bg-amber-500/10 scale-[1.01]'
          : 'border-[#334155] hover:border-amber-500/50 hover:bg-[#1e293b]/50'
        }
        ${compact ? 'p-6' : 'p-16'}
      `}
    >
      <input {...getInputProps()} />

      <div className={`flex flex-col items-center gap-3 text-center ${compact ? '' : 'py-4'}`}>
        <AnimatePresence mode="wait">
          {isDragActive ? (
            <motion.div
              key="drag"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              className="w-14 h-14 bg-amber-500/20 rounded-2xl flex items-center justify-center"
            >
              <Upload className="w-7 h-7 text-amber-400" />
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={{ scale: 0.8, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.8, opacity: 0 }}
              className="w-14 h-14 bg-[#1e293b] rounded-2xl flex items-center justify-center border border-[#334155]"
            >
              <FileText className="w-7 h-7 text-slate-400" />
            </motion.div>
          )}
        </AnimatePresence>

        {compact ? (
          <div>
            <p className="text-sm font-medium text-slate-300">
              {isDragActive ? 'Drop to upload' : 'Drop more PDFs or click to browse'}
            </p>
          </div>
        ) : (
          <div>
            <p className="text-xl font-semibold text-white">
              {isDragActive ? 'Release to upload' : 'Drop your contract PDFs here'}
            </p>
            <p className="text-slate-400 mt-1">
              or <span className="text-amber-400 font-medium">click to browse</span>
            </p>
            <p className="text-xs text-slate-600 mt-3">
              PDF files only · Multiple files supported
            </p>
          </div>
        )}
      </div>

      {/* Animated border glow when dragging */}
      {isDragActive && (
        <motion.div
          layoutId="drop-glow"
          className="absolute inset-0 rounded-2xl pointer-events-none"
          style={{
            boxShadow: '0 0 30px rgba(245, 158, 11, 0.15)',
          }}
        />
      )}
    </motion.div>
  )
}

import { useState } from 'react'
import { motion } from 'framer-motion'
import { Download, CheckCircle } from 'lucide-react'
import confetti from 'canvas-confetti'

export default function DownloadButton({ job }) {
  const [downloaded, setDownloaded] = useState(false)

  const handleDownload = async () => {
    const res = await fetch(`/api/download/${job.job_id}`)
    if (!res.ok) {
      alert('Download failed')
      return
    }

    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    const filename = (job.filename || 'contract').replace('.pdf', '') + '_extracted.xlsm'
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)

    setDownloaded(true)

    // Confetti burst
    confetti({
      particleCount: 120,
      spread: 70,
      origin: { y: 0.6 },
      colors: ['#f59e0b', '#fbbf24', '#10b981', '#60a5fa'],
    })
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="card p-5 flex items-center justify-between"
    >
      <div>
        <h4 className="font-semibold text-white">Your Excel is ready!</h4>
        <p className="text-sm text-slate-400 mt-0.5">
          {(job.rows_extracted || 0).toLocaleString()} rows extracted · XLSM with macros preserved
        </p>
      </div>

      <button
        onClick={handleDownload}
        className={`btn-primary flex items-center gap-2 ${downloaded ? 'bg-emerald-500 hover:bg-emerald-600' : ''}`}
      >
        {downloaded ? (
          <>
            <CheckCircle className="w-4 h-4" />
            Downloaded
          </>
        ) : (
          <>
            <Download className="w-4 h-4" />
            Download Excel
          </>
        )}
      </button>
    </motion.div>
  )
}

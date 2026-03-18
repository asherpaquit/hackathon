import { useState, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Ship, FileSpreadsheet } from 'lucide-react'
import DropZone from './components/DropZone'
import FileQueue from './components/FileQueue'
import ProgressPanel from './components/ProgressPanel'
import PreviewTable from './components/PreviewTable'
import DownloadButton from './components/DownloadButton'
import axios from 'axios'

const API = ''  // Same origin in production; proxied in dev

export default function App() {
  const [jobs, setJobs] = useState([])   // [{job_id, filename, status, ...}]
  const [activeJobId, setActiveJobId] = useState(null)
  const [previewRows, setPreviewRows] = useState([])

  // Derive activeJob directly from the jobs array so it is ALWAYS the latest
  // state — no stale closure possible. Any setJobs call automatically updates
  // what ProgressPanel sees without needing a separate setActiveJob.
  const activeJob = jobs.find(j => j.job_id === activeJobId) || null

  // updateJob only needs to touch setJobs — no dependency on activeJob at all.
  // This makes it a stable reference ([] deps) so WebSocket onmessage handlers
  // never capture a stale version of this callback.
  const updateJob = useCallback((job_id, patch) => {
    setJobs(prev =>
      prev.map(j => {
        if (j.job_id !== job_id) return j
        const updated = { ...j, ...patch }
        // Stamp started_at on first active status transition
        if (!j.started_at && patch.status && patch.status !== 'UPLOADED') {
          updated.started_at = Date.now()
        }
        // Stamp ended_at on terminal status
        if (!j.ended_at && (patch.status === 'COMPLETE' || patch.status === 'ERROR')) {
          updated.ended_at = Date.now()
        }
        return updated
      })
    )
  }, [])

  const startJob = useCallback(async (job_id) => {
    const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsHost = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host
    const ws = new WebSocket(`${wsProto}://${wsHost}/ws/progress/${job_id}`)

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data)
      updateJob(job_id, data)

      if (data.status === 'COMPLETE') {
        ws.close()
        axios.get(`${API}/api/preview/${job_id}`).then(res => {
          setPreviewRows(res.data.rows || [])
        })
      }
    }

    ws.onerror = () => ws.close()

    try {
      await axios.post(`${API}/api/process/${job_id}`)
    } catch (e) {
      updateJob(job_id, { status: 'ERROR', error: e.response?.data?.detail || e.message })
    }
  }, [updateJob])

  const onFilesAccepted = useCallback(async (files) => {
    const form = new FormData()
    files.forEach(f => form.append('files', f))

    let created
    try {
      const res = await axios.post(`${API}/api/upload`, form)
      created = res.data.jobs
    } catch (e) {
      alert('Upload failed: ' + (e.response?.data?.detail || e.message))
      return
    }

    const newJobs = created.map(j => ({
      ...j,
      status: 'UPLOADED',
      stage_pct: 0,
      pages_total: 0,
      pages_done: 0,
      rows_extracted: 0,
      error: null,
    }))
    setJobs(prev => [...prev, ...newJobs])

    for (const j of newJobs) {
      startJob(j.job_id)
    }
  }, [startJob])

  const selectJob = useCallback((job) => {
    setActiveJobId(job.job_id)
    if (job.status === 'COMPLETE') {
      axios.get(`${API}/api/preview/${job.job_id}`).then(res => {
        setPreviewRows(res.data.rows || [])
      })
    }
  }, [])

  const completeJobs = jobs.filter(j => j.status === 'COMPLETE')
  const hasJobs = jobs.length > 0

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="border-b border-[#334155] px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 bg-amber-500 rounded-lg flex items-center justify-center">
            <Ship className="w-5 h-5 text-slate-900" />
          </div>
          <div>
            <h1 className="text-lg font-bold text-white leading-none">FreightScan AI</h1>
            <p className="text-xs text-slate-400 leading-none mt-0.5">PDF Contract → Excel</p>
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-8 space-y-6">
        {/* Hero */}
        {!hasJobs && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center mb-8"
          >
            <div className="inline-flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-full px-4 py-1.5 mb-4">
              <FileSpreadsheet className="w-4 h-4 text-amber-400" />
              <span className="text-sm text-amber-400 font-medium">Freight Contract Digitizer</span>
            </div>
            <h2 className="text-4xl font-bold text-white mb-3">
              Drop your PDF.<br />
              <span className="text-amber-400">Get your Excel.</span>
            </h2>
          </motion.div>
        )}

        {/* Drop Zone */}
        <DropZone onFilesAccepted={onFilesAccepted} compact={hasJobs} />

        {/* Job Queue + Progress + Preview */}
        <AnimatePresence>
          {hasJobs && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              className="grid grid-cols-1 lg:grid-cols-3 gap-6"
            >
              {/* Left: file queue */}
              <div className="lg:col-span-1 space-y-4">
                <FileQueue
                  jobs={jobs}
                  activeJobId={activeJobId}
                  onSelect={selectJob}
                />
              </div>

              {/* Right: progress + preview */}
              <div className="lg:col-span-2 space-y-4">
                {activeJob ? (
                  <>
                    <ProgressPanel key={activeJobId} job={activeJob} />
                    {activeJob.status === 'COMPLETE' && (
                      <>
                        <DownloadButton job={activeJob} />
                        {previewRows.length > 0 && (
                          <PreviewTable rows={previewRows} />
                        )}
                      </>
                    )}
                  </>
                ) : jobs.length > 0 ? (
                  <div className="card p-8 text-center text-slate-400">
                    <FileSpreadsheet className="w-10 h-10 mx-auto mb-3 opacity-30" />
                    <p>Select a file from the queue to see details</p>
                  </div>
                ) : null}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Stats bar when jobs done */}
        {completeJobs.length > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="card p-4 flex items-center gap-6 text-sm"
          >
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span className="text-slate-400">{completeJobs.length} file{completeJobs.length !== 1 ? 's' : ''} processed</span>
            </div>
            <div className="text-slate-400">
              {completeJobs.reduce((sum, j) => sum + (j.rows_extracted || 0), 0).toLocaleString()} total rows extracted
            </div>
          </motion.div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-[#334155] px-6 py-4 text-center text-xs text-slate-600">
        FreightScan AI · Built for SoftPoint Hackathon 2026
      </footer>
    </div>
  )
}

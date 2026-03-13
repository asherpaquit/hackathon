import { useMemo, useState } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getFilteredRowModel,
  flexRender,
} from '@tanstack/react-table'
import { Search } from 'lucide-react'

const COLUMNS = [
  { accessorKey: 'carrier',          header: 'Carrier',        size: 80 },
  { accessorKey: 'contract_id',      header: 'Contract',       size: 110 },
  { accessorKey: 'origin_city',      header: 'Origin',         size: 130 },
  { accessorKey: 'destination_city', header: 'Destination',    size: 160 },
  { accessorKey: 'service',          header: 'Service',        size: 80 },
  { accessorKey: 'scope',            header: 'Scope',          size: 200 },
  { accessorKey: 'base_rate_20',     header: "20'",            size: 60 },
  { accessorKey: 'base_rate_40',     header: "40'",            size: 60 },
  { accessorKey: 'base_rate_40h',    header: "40H",            size: 60 },
  { accessorKey: 'base_rate_45',     header: "45'",            size: 60 },
  { accessorKey: 'ams_china_japan',  header: 'AMS',            size: 55 },
]

export default function PreviewTable({ rows }) {
  const [globalFilter, setGlobalFilter] = useState('')

  const columns = useMemo(() => COLUMNS.map(col => ({
    ...col,
    cell: ({ getValue }) => {
      const val = getValue()
      if (val === null || val === undefined || val === '') return (
        <span className="text-slate-600">—</span>
      )
      if (typeof val === 'number') return (
        <span className="font-mono text-amber-300">{val.toLocaleString()}</span>
      )
      return val
    },
  })), [])

  const table = useReactTable({
    data: rows,
    columns,
    state: { globalFilter },
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  const filtered = table.getRowModel().rows

  return (
    <div className="card overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#334155] flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-white">Data Preview</h3>
          <span className="badge badge-slate">{filtered.length.toLocaleString()} rows</span>
        </div>

        <div className="relative">
          <Search className="absolute left-2.5 top-2 w-3.5 h-3.5 text-slate-500" />
          <input
            value={globalFilter}
            onChange={e => setGlobalFilter(e.target.value)}
            placeholder="Filter…"
            className="bg-[#0f172a] border border-[#334155] rounded-lg pl-8 pr-3 py-1.5 text-sm text-white placeholder-slate-600 focus:outline-none focus:border-amber-500 w-48"
          />
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto max-h-96">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[#1e293b] border-b border-[#334155]">
            {table.getHeaderGroups().map(hg => (
              <tr key={hg.id}>
                {hg.headers.map(header => (
                  <th
                    key={header.id}
                    className="px-3 py-2.5 text-left text-slate-400 font-medium whitespace-nowrap"
                    style={{ width: header.column.columnDef.size }}
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {filtered.slice(0, 200).map((row, i) => (
              <tr
                key={row.id}
                className={`border-b border-[#334155]/50 hover:bg-[#334155]/20 transition-colors ${
                  i % 2 === 0 ? '' : 'bg-[#0f172a]/30'
                }`}
              >
                {row.getVisibleCells().map(cell => (
                  <td key={cell.id} className="px-3 py-2 whitespace-nowrap text-slate-300">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>

        {filtered.length > 200 && (
          <div className="px-4 py-3 text-xs text-slate-500 text-center border-t border-[#334155]">
            Showing first 200 of {filtered.length.toLocaleString()} rows — download Excel for full data
          </div>
        )}
        {filtered.length === 0 && (
          <div className="px-4 py-8 text-sm text-slate-500 text-center">
            No rows match your filter
          </div>
        )}
      </div>
    </div>
  )
}

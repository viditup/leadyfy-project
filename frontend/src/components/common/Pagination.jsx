import { ChevronLeft, ChevronRight } from 'lucide-react';

export default function Pagination({ page, pageCount, total, pageSize, onChange }) {
  if (total === 0) return null;
  const start = (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return (
    <div className="table-footer">
      <span>
        Showing {start}–{end} of {total}
      </span>
      <div className="flex gap-8">
        <button className="icon-btn" disabled={page <= 1} onClick={() => onChange(page - 1)} aria-label="Previous page">
          <ChevronLeft size={15} />
        </button>
        <span className="flex" style={{ padding: '0 4px' }}>
          Page {page} of {pageCount || 1}
        </span>
        <button className="icon-btn" disabled={page >= pageCount} onClick={() => onChange(page + 1)} aria-label="Next page">
          <ChevronRight size={15} />
        </button>
      </div>
    </div>
  );
}

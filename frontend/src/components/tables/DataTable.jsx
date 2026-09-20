import { useMemo, useState } from 'react';
import { ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react';
import Pagination from '../common/Pagination';
import { EmptyState } from '../common/States';

// columns: [{ key, label, render?(row), sortable?, align? }]
export default function DataTable({ columns, rows, rowKey = 'id', pageSize = 8, emptyTitle, emptyDescription, renderRowActions }) {
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState({ key: null, dir: 'asc' });

  const sorted = useMemo(() => {
    if (!sort.key) return rows;
    return [...rows].sort((a, b) => {
      const av = a[sort.key];
      const bv = b[sort.key];
      if (typeof av === 'number' && typeof bv === 'number') return sort.dir === 'asc' ? av - bv : bv - av;
      return sort.dir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  }, [rows, sort]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / pageSize));
  const current = Math.min(page, pageCount);
  const pageRows = sorted.slice((current - 1) * pageSize, current * pageSize);

  function toggleSort(key) {
    setSort((prev) => (prev.key === key ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' }));
  }

  if (rows.length === 0) {
    return <EmptyState title={emptyTitle || 'No records yet'} description={emptyDescription} />;
  }

  return (
    <>
      <div style={{ overflowX: 'auto' }}>
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  style={{ cursor: col.sortable ? 'pointer' : 'default', textAlign: col.align || 'left' }}
                  onClick={() => col.sortable && toggleSort(col.key)}
                >
                  <span className="flex gap-6">
                    {col.label}
                    {col.sortable &&
                      (sort.key === col.key ? (
                        sort.dir === 'asc' ? (
                          <ArrowUp size={12} />
                        ) : (
                          <ArrowDown size={12} />
                        )
                      ) : (
                        <ArrowUpDown size={11} style={{ opacity: 0.4 }} />
                      ))}
                  </span>
                </th>
              ))}
              {renderRowActions && <th style={{ textAlign: 'right' }}>Actions</th>}
            </tr>
          </thead>
          <tbody>
            {pageRows.map((row) => (
              <tr key={row[rowKey]}>
                {columns.map((col) => (
                  <td key={col.key} style={{ textAlign: col.align || 'left' }}>
                    {col.render ? col.render(row) : row[col.key]}
                  </td>
                ))}
                {renderRowActions && (
                  <td>
                    <div className="row-actions">{renderRowActions(row)}</div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination page={current} pageCount={pageCount} total={sorted.length} pageSize={pageSize} onChange={setPage} />
    </>
  );
}

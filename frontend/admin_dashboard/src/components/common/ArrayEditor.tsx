import React, { useState } from 'react';
import { useT } from '../../lib/i18n';
import type { ReactNode } from 'react';

interface ArrayEditorProps<T> {
  items: T[];
  onAdd: () => void;
  onEdit: (index: number, newData: T) => void;
  onDelete: (index: number) => void;
  onReorder?: (fromIndex: number, toIndex: number) => void;
  renderItem: (item: T, index: number, onEdit: (newData: T) => void) => ReactNode;
  addButtonText?: string;
  emptyMessage?: string;
  allowReorder?: boolean;
}

/**
 * An editable list of sub-records — a form template's questions, a grade
 * scale's bands, a guardian's contact numbers.
 *
 * Reordering is drag-and-drop on a desktop and **arrow buttons on a phone**,
 * because HTML5 drag events do not fire from touch at all. Two ways in, one
 * `onReorder` — a screen that only worked with a mouse would leave the grade
 * scale uneditable from the office phone.
 */
export default function ArrayEditor<T>({
  items,
  onAdd,
  onEdit,
  onDelete,
  onReorder,
  renderItem,
  addButtonText,
  emptyMessage,
  allowReorder = false,
}: ArrayEditorProps<T>) {
  const { t } = useT();
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);

  const reorderable = allowReorder && !!onReorder;

  const move = (from: number, to: number) => {
    if (!onReorder) return;
    if (to < 0 || to >= items.length || to === from) return;
    onReorder(from, to);
  };

  const handleDrop = (e: React.DragEvent, dropIndex: number) => {
    e.preventDefault();
    if (draggedIndex !== null) move(draggedIndex, dropIndex);
    setDraggedIndex(null);
  };

  return (
    <div className="space-y-4">
      {items.length === 0 ? (
        <div className="rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 py-8 text-center">
          <p className="text-sm text-gray-500">
            {emptyMessage || t('No items yet. Click the button below to add one.')}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item, index) => (
            <div
              key={index}
              className={`relative rounded-lg border-2 bg-gray-50 p-3 sm:p-4 ${
                draggedIndex === index ? 'border-blue-500 opacity-50' : 'border-gray-200'
              }`}
              draggable={reorderable}
              onDragStart={() => setDraggedIndex(index)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => handleDrop(e, index)}
              onDragEnd={() => setDraggedIndex(null)}
            >
              {/* Delete sits in the flow rather than absolutely positioned in
                  the corner: an overlaid button lands on top of whatever the
                  row's own content is at 360px. */}
              <div className="flex items-start gap-2">
                {reorderable && (
                  <div className="flex shrink-0 flex-col">
                    <button
                      type="button"
                      onClick={() => move(index, index - 1)}
                      disabled={index === 0}
                      aria-label={t('Back')}
                      className="tap min-h-[36px] rounded text-gray-400 hover:bg-white hover:text-gray-700 disabled:opacity-30"
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      onClick={() => move(index, index + 1)}
                      disabled={index === items.length - 1}
                      aria-label={t('Next')}
                      className="tap min-h-[36px] rounded text-gray-400 hover:bg-white hover:text-gray-700 disabled:opacity-30"
                    >
                      ↓
                    </button>
                  </div>
                )}

                <div className="min-w-0 flex-1">
                  {renderItem(item, index, (newData) => onEdit(index, newData))}
                </div>

                <button
                  type="button"
                  onClick={() => onDelete(index)}
                  className="tap shrink-0 rounded text-red-600 transition-colors hover:bg-red-50 hover:text-red-700"
                  title={t('Delete item')}
                  aria-label={t('Delete item')}
                >
                  <svg
                    className="h-5 w-5"
                    fill="none"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={onAdd}
        className="tap w-full gap-2 rounded-lg bg-blue-600 px-4 font-medium text-white transition-colors hover:bg-blue-700"
      >
        <svg
          className="h-5 w-5"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path d="M12 4v16m8-8H4" />
        </svg>
        {addButtonText || t('Add Item')}
      </button>
    </div>
  );
}

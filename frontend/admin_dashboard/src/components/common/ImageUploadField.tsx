import React, { useRef, useState } from 'react';
import { useT } from '../../lib/i18n';

interface ImageUploadFieldProps {
  label: string;
  /** The image already saved, as a URL. */
  value?: string;
  onChange: (file: File | null, previewUrl?: string) => void;
  accept?: string;
  /** Megabytes. */
  maxSize?: number;
  helperText?: string;
  preview?: boolean;
}

/**
 * One image field — a student's photo, a teacher's photo, an institution's
 * logo. Drag-and-drop on a desktop, a tap that opens the camera on a phone.
 *
 * `capture` is deliberately NOT set: a student photo is as often an existing
 * picture from the gallery as a new one, and forcing the camera would make the
 * common case impossible.
 */
export default function ImageUploadField({
  label,
  value,
  onChange,
  accept = 'image/jpeg,image/png,image/webp',
  maxSize = 5,
  helperText,
  preview = true,
}: ImageUploadFieldProps) {
  const { t } = useT();
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState(value || '');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validate = (file: File): string | null => {
    const accepted = accept.split(',').map((s) => s.trim());
    if (!accepted.includes(file.type)) {
      return `${t('Please select a valid image file')} (${accept})`;
    }
    if (file.size / (1024 * 1024) > maxSize) {
      return `${t('File size must be less than')} ${maxSize}MB`;
    }
    return null;
  };

  const handleFile = (file: File) => {
    const problem = validate(file);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    onChange(file, url);
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
    else if (e.type === 'dragleave') setDragActive(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  };

  const openPicker = () => fileInputRef.current?.click();

  const handleRemove = () => {
    setPreviewUrl('');
    setError(null);
    onChange(null);
    // Clearing the input's value matters: without it, re-picking the SAME file
    // fires no change event and the field appears to ignore the choice.
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="mb-4">
      <label className="mb-2 block text-sm font-medium text-gray-700">{label}</label>

      <div
        className={`relative rounded-lg border-2 border-dashed p-4 text-center transition-colors sm:p-6 ${
          error
            ? 'border-red-500 bg-red-50'
            : dragActive
              ? 'border-blue-500 bg-blue-50'
              : previewUrl
                ? 'border-emerald-300 bg-emerald-50'
                : 'border-gray-300 bg-gray-50'
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={accept}
          onChange={handleChange}
          className="hidden"
        />

        {preview && previewUrl ? (
          <div className="space-y-3">
            <img
              src={previewUrl}
              alt={t('Preview')}
              className="mx-auto max-h-48 rounded-lg shadow-md"
            />
            {/* Stacked on a phone: two buttons side by side at 360px are two
                buttons too narrow to hit. */}
            <div className="flex flex-col justify-center gap-2 sm:flex-row">
              <button
                type="button"
                onClick={openPicker}
                className="tap rounded-lg bg-blue-600 px-4 text-sm font-medium text-white transition-colors hover:bg-blue-700"
              >
                {t('Change Image')}
              </button>
              <button
                type="button"
                onClick={handleRemove}
                className="tap rounded-lg bg-red-600 px-4 text-sm font-medium text-white transition-colors hover:bg-red-700"
              >
                {t('Remove')}
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            <svg
              className="mx-auto h-10 w-10 text-gray-400 sm:h-12 sm:w-12"
              stroke="currentColor"
              fill="none"
              viewBox="0 0 48 48"
              aria-hidden="true"
            >
              <path
                d="M28 8H12a4 4 0 00-4 4v20m32-12v8m0 0v8a4 4 0 01-4 4H12a4 4 0 01-4-4v-4m32-4l-3.172-3.172a4 4 0 00-5.656 0L28 28M8 32l9.172-9.172a4 4 0 015.656 0L28 28m0 0l4 4m4-24h8m-4-4v8m-12 4h.02"
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <div className="text-sm text-gray-600">
              <button
                type="button"
                onClick={openPicker}
                className="tap px-2 font-medium text-blue-600 hover:text-blue-500"
              >
                {t('Upload a file')}
              </button>
              {/* Drag-and-drop is meaningless on a touch screen and only makes
                  the instruction longer where it is already tightest. */}
              <span className="hidden sm:inline"> {t('or drag and drop')}</span>
            </div>
            <p className="text-xs text-gray-500">
              {accept.replace(/image\//g, '').toUpperCase()} {t('up to')} {maxSize}MB
            </p>
          </div>
        )}
      </div>

      {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
      {helperText && !error && <p className="mt-1 text-xs text-gray-500">{helperText}</p>}
    </div>
  );
}

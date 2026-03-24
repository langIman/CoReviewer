import { useCallback } from 'react'
import { useReviewStore } from '../store/useReviewStore'
import { uploadFile } from '../services/api'

export default function UploadBar() {
  const { file, setFile } = useReviewStore()

  const handleUpload = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0]
      if (!f) return
      try {
        const data = await uploadFile(f)
        setFile(data)
      } catch (err: unknown) {
        alert(err instanceof Error ? err.message : 'Upload failed')
      }
    },
    [setFile]
  )

  const handleDrop = useCallback(
    async (e: React.DragEvent) => {
      e.preventDefault()
      const f = e.dataTransfer.files[0]
      if (!f) return
      try {
        const data = await uploadFile(f)
        setFile(data)
      } catch (err: unknown) {
        alert(err instanceof Error ? err.message : 'Upload failed')
      }
    },
    [setFile]
  )

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-gray-50 border-b border-gray-200">
      <span className="text-sm font-semibold text-gray-700">CoReviewer</span>
      <div className="h-4 w-px bg-gray-300" />
      <label
        className="cursor-pointer text-sm text-blue-600 hover:text-blue-800"
        onDragOver={(e) => e.preventDefault()}
        onDrop={handleDrop}
      >
        {file ? file.filename : 'Upload .py file (click or drag)'}
        <input
          type="file"
          accept=".py"
          className="hidden"
          onChange={handleUpload}
        />
      </label>
      {file && (
        <span className="text-xs text-gray-400">
          {file.line_count} lines
        </span>
      )}
    </div>
  )
}

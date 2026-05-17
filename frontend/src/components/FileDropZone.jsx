import { useRef, useCallback } from 'react'

export default function FileDropZone({ onFileSelect, accept, label, sublabel, fileName }) {
  const inputRef = useRef(null)

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    e.currentTarget.style.borderColor = 'var(--accent-primary)'
  }, [])

  const handleDragLeave = useCallback((e) => {
    e.preventDefault()
    e.currentTarget.style.borderColor = 'var(--glass-border)'
  }, [])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    e.currentTarget.style.borderColor = 'var(--glass-border)'
    if (e.dataTransfer.files[0]) {
      onFileSelect(e.dataTransfer.files[0])
    }
  }, [onFileSelect])

  const handleChange = useCallback((e) => {
    if (e.target.files[0]) {
      onFileSelect(e.target.files[0])
    }
  }, [onFileSelect])

  return (
    <div
      className="upload-zone"
      onClick={() => inputRef.current?.click()}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div style={{ width: 40, height: 40, color: 'var(--accent-primary)' }}>☁</div>
      <h3 style={{ fontSize: 16, marginTop: 8 }}>{label || 'Drag & Drop File'}</h3>
      <p className="text-secondary mt-8" style={{ fontSize: 12 }}>{sublabel || 'or click to browse'}</p>
      <input ref={inputRef} type="file" accept={accept} hidden onChange={handleChange} />
      {fileName && (
        <p className="mt-16 text-muted" style={{ fontSize: 13 }}>Uploaded: {fileName}</p>
      )}
    </div>
  )
}

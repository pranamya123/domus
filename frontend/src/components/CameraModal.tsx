import { useState, useRef } from 'react'
import { X, Camera, Upload, Check, Loader2, Image } from 'lucide-react'

interface CameraModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function CameraModal({ isOpen, onClose }: CameraModalProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [result, setResult] = useState<{
    success: boolean
    message: string
    items?: string[]
  } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  if (!isOpen) return null

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.type.startsWith('image/')) {
      setResult({ success: false, message: 'Please select an image file' })
      return
    }

    setSelectedFile(file)
    setResult(null)

    const reader = new FileReader()
    reader.onloadend = () => setPreview(reader.result as string)
    reader.readAsDataURL(file)
  }

  const handleUpload = async () => {
    if (!selectedFile) return

    setIsUploading(true)

    try {
      const formData = new FormData()
      formData.append('file', selectedFile)

      const response = await fetch('/api/upload/image', {
        method: 'POST',
        body: formData
      })

      const data = await response.json()

      setResult({
        success: data.validation_passed && data.status === 'success',
        message: data.message,
        items: data.items_detected
      })

      if (data.validation_passed && data.status === 'success') {
        setTimeout(() => {
          handleClose()
        }, 2000)
      }
    } catch (error) {
      setResult({ success: false, message: 'Upload failed. Please try again.' })
    } finally {
      setIsUploading(false)
    }
  }

  const handleClose = () => {
    setSelectedFile(null)
    setPreview(null)
    setResult(null)
    onClose()
  }

  const clearSelection = () => {
    setSelectedFile(null)
    setPreview(null)
    setResult(null)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
      <div className="bg-[#212121] rounded-2xl w-full max-w-md max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h2 className="text-lg font-semibold text-white">Scan Fridge</h2>
          <button
            onClick={handleClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4">
          {!preview ? (
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-white/20 hover:border-cyan-400/50 rounded-2xl p-8 text-center cursor-pointer transition-colors"
            >
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                capture="environment"
                onChange={handleFileSelect}
                className="hidden"
              />
              <div className="w-16 h-16 bg-cyan-500/10 rounded-2xl flex items-center justify-center mx-auto mb-4">
                <Camera className="w-8 h-8 text-cyan-400" />
              </div>
              <h3 className="text-white font-medium mb-2">Take a Photo</h3>
              <p className="text-sm text-gray-400 mb-4">
                Capture or upload an image of your fridge
              </p>
              <div className="flex gap-4 justify-center text-sm text-gray-500">
                <span className="flex items-center gap-1">
                  <Camera className="w-4 h-4" /> Camera
                </span>
                <span className="flex items-center gap-1">
                  <Upload className="w-4 h-4" /> Upload
                </span>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="relative rounded-xl overflow-hidden">
                <img
                  src={preview}
                  alt="Preview"
                  className="w-full aspect-[4/3] object-cover"
                />
                <button
                  onClick={clearSelection}
                  className="absolute top-2 right-2 p-2 bg-black/60 hover:bg-black/80 rounded-full"
                >
                  <X className="w-4 h-4 text-white" />
                </button>
              </div>

              {result && (
                <div className={`p-4 rounded-xl ${
                  result.success
                    ? 'bg-green-500/10 border border-green-500/30'
                    : 'bg-red-500/10 border border-red-500/30'
                }`}>
                  <div className="flex items-start gap-2">
                    {result.success ? (
                      <Check className="w-5 h-5 text-green-400 mt-0.5" />
                    ) : (
                      <X className="w-5 h-5 text-red-400 mt-0.5" />
                    )}
                    <div>
                      <p className={result.success ? 'text-green-400' : 'text-red-400'}>
                        {result.success ? 'Scan Complete!' : 'Scan Failed'}
                      </p>
                      <p className="text-sm text-gray-400 mt-1">{result.message}</p>
                      {result.items && result.items.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {result.items.slice(0, 6).map((item, i) => (
                            <span key={i} className="px-2 py-0.5 bg-white/10 rounded text-xs text-gray-300">
                              {item}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  onClick={clearSelection}
                  className="flex-1 py-3 bg-white/5 hover:bg-white/10 rounded-xl text-white transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleUpload}
                  disabled={isUploading || result?.success}
                  className="flex-1 py-3 bg-cyan-500 hover:bg-cyan-600 disabled:bg-cyan-500/30 rounded-xl text-white font-medium transition-colors flex items-center justify-center gap-2"
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Analyzing...
                    </>
                  ) : result?.success ? (
                    <>
                      <Check className="w-5 h-5" />
                      Done
                    </>
                  ) : (
                    <>
                      <Image className="w-5 h-5" />
                      Analyze
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

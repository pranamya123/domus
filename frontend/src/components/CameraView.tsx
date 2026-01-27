/**
 * Camera View Component
 * Handles fridge image capture and upload
 */

import { useState, useRef, useCallback } from 'react'
import { Camera, Upload, Check, X, Loader2, Image } from 'lucide-react'
import { api } from '../services/api'
import { useStore } from '../store/useStore'

export default function CameraView() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState<{
    success: boolean
    message: string
    items?: string[]
  } | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const { setAppState } = useStore()

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    // Validate file type
    if (!file.type.startsWith('image/')) {
      setUploadResult({
        success: false,
        message: 'Please select an image file',
      })
      return
    }

    setSelectedFile(file)
    setUploadResult(null)

    // Create preview
    const reader = new FileReader()
    reader.onloadend = () => {
      setPreview(reader.result as string)
    }
    reader.readAsDataURL(file)
  }, [])

  const handleUpload = async () => {
    if (!selectedFile) return

    setIsUploading(true)
    setAppState('CONNECTED_SCANNING')

    try {
      const result = await api.uploadImage(selectedFile)

      setUploadResult({
        success: result.validation_passed && result.status === 'success',
        message: result.message,
        items: result.items_detected,
      })

      if (result.validation_passed && result.status === 'success') {
        // Clear selection after successful upload
        setTimeout(() => {
          setSelectedFile(null)
          setPreview(null)
        }, 3000)
      }
    } catch (error) {
      console.error('Upload error:', error)
      setUploadResult({
        success: false,
        message: 'Upload failed. Please try again.',
      })
    } finally {
      setIsUploading(false)
      setAppState('CONNECTED_IDLE')
    }
  }

  const clearSelection = () => {
    setSelectedFile(null)
    setPreview(null)
    setUploadResult(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  return (
    <div className="h-full flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Upload area */}
        {!preview ? (
          <div
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-white/20 hover:border-domus-primary rounded-2xl p-8 text-center cursor-pointer transition-colors"
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              capture="environment"
              onChange={handleFileSelect}
              className="hidden"
            />
            <div className="inline-flex items-center justify-center w-16 h-16 bg-domus-primary/10 rounded-2xl mb-4">
              <Camera className="w-8 h-8 text-domus-primary" />
            </div>
            <h3 className="text-lg font-medium text-white mb-2">
              Scan Your Fridge
            </h3>
            <p className="text-gray-400 text-sm mb-4">
              Take a photo or upload an image of the inside of your fridge
            </p>
            <div className="flex gap-4 justify-center">
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Camera className="w-4 h-4" />
                <span>Take Photo</span>
              </div>
              <div className="flex items-center gap-2 text-sm text-gray-400">
                <Upload className="w-4 h-4" />
                <span>Upload</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {/* Preview */}
            <div className="relative rounded-2xl overflow-hidden bg-domus-dark-100">
              <img
                src={preview}
                alt="Fridge preview"
                className="w-full aspect-[4/3] object-cover"
              />
              <button
                onClick={clearSelection}
                className="absolute top-2 right-2 p-2 bg-black/50 hover:bg-black/70 rounded-full transition-colors"
              >
                <X className="w-5 h-5 text-white" />
              </button>
            </div>

            {/* Upload result */}
            {uploadResult && (
              <div
                className={`p-4 rounded-xl ${
                  uploadResult.success
                    ? 'bg-green-500/10 border border-green-500/20'
                    : 'bg-red-500/10 border border-red-500/20'
                }`}
              >
                <div className="flex items-start gap-3">
                  {uploadResult.success ? (
                    <Check className="w-5 h-5 text-green-500 mt-0.5" />
                  ) : (
                    <X className="w-5 h-5 text-red-500 mt-0.5" />
                  )}
                  <div>
                    <p
                      className={`font-medium ${
                        uploadResult.success ? 'text-green-400' : 'text-red-400'
                      }`}
                    >
                      {uploadResult.success ? 'Scan Complete!' : 'Scan Failed'}
                    </p>
                    <p className="text-sm text-gray-400 mt-1">
                      {uploadResult.message}
                    </p>
                    {uploadResult.items && uploadResult.items.length > 0 && (
                      <div className="mt-3">
                        <p className="text-xs text-gray-500 mb-2">Detected items:</p>
                        <div className="flex flex-wrap gap-1">
                          {uploadResult.items.map((item, i) => (
                            <span
                              key={i}
                              className="px-2 py-1 bg-white/5 rounded text-xs text-gray-300"
                            >
                              {item}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-3">
              <button
                onClick={clearSelection}
                className="flex-1 px-4 py-3 bg-white/5 hover:bg-white/10 rounded-xl text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleUpload}
                disabled={isUploading || uploadResult?.success}
                className="flex-1 px-4 py-3 bg-domus-primary hover:bg-domus-primary/90 disabled:bg-domus-primary/30 rounded-xl text-white transition-colors flex items-center justify-center gap-2"
              >
                {isUploading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Analyzing...
                  </>
                ) : uploadResult?.success ? (
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

        {/* Tips */}
        <div className="mt-8 space-y-2">
          <p className="text-sm text-gray-500 text-center">Tips for best results:</p>
          <ul className="text-xs text-gray-500 space-y-1">
            <li className="flex items-start gap-2">
              <span className="text-domus-primary">•</span>
              <span>Make sure the fridge is well-lit</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-domus-primary">•</span>
              <span>Capture all shelves if possible</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-domus-primary">•</span>
              <span>Keep items visible and not overlapping</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  )
}

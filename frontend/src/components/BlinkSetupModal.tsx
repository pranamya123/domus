import { useState, useEffect } from 'react'
import { X, Camera, Wifi, Check, Loader2, AlertCircle, Eye, EyeOff } from 'lucide-react'
import { useStore } from '../store/useStore'

interface BlinkSetupModalProps {
  isOpen: boolean
  onClose: () => void
}

interface BlinkStatus {
  initialized: boolean
  monitoring: boolean
  cameras: Array<{
    name: string
    id: string
    type: string
    armed: boolean
    battery: string
    temperature: number
  }>
  credentials_saved: boolean
}

interface FridgeState {
  latest_image_url?: string
  item_count: number
  last_analysis?: {
    timestamp: string
  }
}

export default function BlinkSetupModal({ isOpen, onClose }: BlinkSetupModalProps) {
  const [step, setStep] = useState<'status' | 'login' | '2fa' | 'connected'>('status')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [code2fa, setCode2fa] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [status, setStatus] = useState<BlinkStatus | null>(null)
  const [fridgeState, setFridgeState] = useState<FridgeState | null>(null)

  const { setBlinkStatus } = useStore()

  useEffect(() => {
    if (isOpen) {
      checkStatus()
    }
  }, [isOpen])

  const updateGlobalStatus = (initialized: boolean, monitoring: boolean) => {
    setBlinkStatus(initialized, monitoring)
  }

  const fetchFridgeState = async () => {
    try {
      const response = await fetch('/api/fridge/state')
      const data = await response.json()
      if (data.status === 'success') {
        setFridgeState({
          latest_image_url: data.latest_image_url,
          item_count: data.item_count || 0,
          last_analysis: data.last_updated ? { timestamp: data.last_updated } : undefined
        })
      }
    } catch (err) {
      console.error('Failed to fetch fridge state:', err)
    }
  }

  const checkStatus = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/blink/status')
      const data = await response.json()
      setStatus(data)
      updateGlobalStatus(data.initialized, data.monitoring)

      if (data.initialized) {
        setStep('connected')
        // Fetch latest fridge state to show the image
        await fetchFridgeState()
        // Auto-start monitoring if not already monitoring
        if (!data.monitoring) {
          await startMonitoring()
        }
      } else if (data.credentials_saved) {
        await reconnect()
      } else {
        setStep('login')
      }
    } catch (err) {
      setError('Failed to check Blink status')
    } finally {
      setLoading(false)
    }
  }

  const startMonitoring = async () => {
    try {
      await fetch('/api/blink/monitoring/start', { method: 'POST' })
      const response = await fetch('/api/blink/status')
      const data = await response.json()
      setStatus(data)
      updateGlobalStatus(data.initialized, data.monitoring)
    } catch (err) {
      console.error('Failed to start monitoring:', err)
    }
  }

  const reconnect = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/blink/reconnect', { method: 'POST' })
      const data = await response.json()

      if (data.status === 'success') {
        setStatus({ ...status!, initialized: true, cameras: data.cameras })
        updateGlobalStatus(true, false)
        setStep('connected')
        // Auto-start monitoring after reconnect
        await startMonitoring()
      } else if (data.status === '2fa_required') {
        setStep('2fa')
      } else {
        setStep('login')
      }
    } catch (err) {
      setStep('login')
    } finally {
      setLoading(false)
    }
  }

  const handleLogin = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/blink/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      })
      const data = await response.json()

      if (data.status === 'success') {
        setStatus({ ...status!, initialized: true, cameras: data.cameras })
        updateGlobalStatus(true, false)
        setStep('connected')
        // Auto-start monitoring after login
        await startMonitoring()
      } else if (data.status === '2fa_required') {
        setStep('2fa')
      } else {
        setError(data.message || 'Login failed')
      }
    } catch (err: any) {
      setError(err.message || 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  const handleVerify2FA = async () => {
    setLoading(true)
    setError('')
    try {
      const response = await fetch('/api/blink/verify-2fa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code2fa })
      })
      const data = await response.json()

      if (data.status === 'success') {
        setStatus({ ...status!, initialized: true, cameras: data.cameras })
        updateGlobalStatus(true, false)
        setStep('connected')
        // Auto-start monitoring after 2FA
        await startMonitoring()
      } else {
        setError(data.message || 'Verification failed')
      }
    } catch (err: any) {
      setError(err.message || 'Verification failed')
    } finally {
      setLoading(false)
    }
  }

  const handleDisconnect = async () => {
    setLoading(true)
    try {
      await fetch('/api/blink/disconnect', { method: 'POST' })
      setStatus(null)
      updateGlobalStatus(false, false)
      setStep('login')
      setEmail('')
      setPassword('')
    } catch (err) {
      setError('Disconnect failed')
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
      <div className="bg-[#212121] rounded-2xl w-full max-w-md max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div className="flex items-center gap-2">
            <Camera className="w-5 h-5 text-cyan-400" />
            <h2 className="text-lg font-semibold text-white">
              {step === 'connected' ? 'Camera Settings' : 'Connect Camera'}
            </h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg">
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {/* Error Banner */}
          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-xl flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-red-400" />
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          {/* Loading */}
          {loading && step === 'status' && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
            </div>
          )}

          {/* Login Step */}
          {step === 'login' && (
            <div className="space-y-4">
              <div className="text-center mb-6">
                <div className="w-16 h-16 bg-cyan-500/10 rounded-2xl flex items-center justify-center mx-auto mb-3">
                  <Camera className="w-8 h-8 text-cyan-400" />
                </div>
                <h3 className="text-white font-medium">Connect Blink Camera</h3>
                <p className="text-sm text-gray-400 mt-1">Login with your Blink/Amazon account</p>
              </div>

              <div>
                <label className="text-sm text-gray-400 mb-1 block">Email</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="text-sm text-gray-400 mb-1 block">Password</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Your Blink password"
                    className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:border-cyan-500 focus:outline-none pr-12"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 hover:bg-white/10 rounded"
                  >
                    {showPassword ? (
                      <EyeOff className="w-5 h-5 text-gray-400" />
                    ) : (
                      <Eye className="w-5 h-5 text-gray-400" />
                    )}
                  </button>
                </div>
              </div>

              <button
                onClick={handleLogin}
                disabled={loading || !email || !password}
                className="w-full py-3 bg-cyan-500 hover:bg-cyan-600 disabled:bg-cyan-500/50 text-white font-medium rounded-xl transition-colors flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Connecting...
                  </>
                ) : (
                  <>
                    <Wifi className="w-5 h-5" />
                    Connect
                  </>
                )}
              </button>

              <p className="text-xs text-gray-500 text-center">
                Your credentials are stored locally and only used to connect to Blink.
              </p>
            </div>
          )}

          {/* 2FA Step */}
          {step === '2fa' && (
            <div className="space-y-4">
              <div className="text-center mb-6">
                <div className="w-16 h-16 bg-blue-500/10 rounded-2xl flex items-center justify-center mx-auto mb-3">
                  <AlertCircle className="w-8 h-8 text-blue-400" />
                </div>
                <h3 className="text-white font-medium">Two-Factor Authentication</h3>
                <p className="text-sm text-gray-400 mt-1">
                  Check your email/phone for a verification code from Blink
                </p>
              </div>

              <div>
                <label className="text-sm text-gray-400 mb-1 block">Verification Code</label>
                <input
                  type="text"
                  value={code2fa}
                  onChange={(e) => setCode2fa(e.target.value)}
                  placeholder="Enter 6-digit code"
                  maxLength={6}
                  className="w-full bg-black/30 border border-white/10 rounded-xl px-4 py-3 text-white text-center text-2xl tracking-widest placeholder-gray-500 focus:border-cyan-500 focus:outline-none"
                />
              </div>

              <button
                onClick={handleVerify2FA}
                disabled={loading || code2fa.length < 4}
                className="w-full py-3 bg-cyan-500 hover:bg-cyan-600 disabled:bg-cyan-500/50 text-white font-medium rounded-xl transition-colors flex items-center justify-center gap-2"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Verifying...
                  </>
                ) : (
                  <>
                    <Check className="w-5 h-5" />
                    Verify
                  </>
                )}
              </button>
            </div>
          )}

          {/* Connected Step - Simplified */}
          {step === 'connected' && status && (
            <div className="space-y-4">
              {/* Status Banner */}
              <div className="p-4 bg-green-500/10 border border-green-500/30 rounded-xl">
                <div className="flex items-center gap-3">
                  <Check className="w-6 h-6 text-green-400" />
                  <div>
                    <p className="text-green-400 font-medium">Camera Connected</p>
                    <p className="text-sm text-gray-400">{status.cameras.length} camera(s) found</p>
                  </div>
                </div>
              </div>

              {/* Latest Capture */}
              {fridgeState?.latest_image_url && (
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-sm text-gray-400">Latest Capture</h4>
                    {fridgeState.item_count > 0 && (
                      <span className="text-xs text-cyan-400">{fridgeState.item_count} items detected</span>
                    )}
                  </div>
                  <div className="rounded-xl overflow-hidden border border-white/10">
                    <img
                      src={fridgeState.latest_image_url}
                      alt="Latest fridge capture"
                      className="w-full h-48 object-cover bg-black"
                    />
                  </div>
                  {fridgeState.last_analysis?.timestamp && (
                    <p className="text-xs text-gray-500 mt-1">
                      Captured {new Date(fridgeState.last_analysis.timestamp).toLocaleString()}
                    </p>
                  )}
                </div>
              )}

              {/* Auto-monitoring status */}
              <div className="p-4 bg-cyan-500/10 border border-cyan-500/30 rounded-xl">
                <div className="flex items-center gap-2 text-cyan-400">
                  <div className="w-2 h-2 bg-cyan-400 rounded-full animate-pulse" />
                  <span className="font-medium">Auto-Capture Active</span>
                </div>
                <p className="text-sm text-gray-400 mt-2">
                  Your fridge will be scanned automatically whenever the door opens.
                </p>
              </div>

              {/* Cameras */}
              <div>
                <h4 className="text-sm text-gray-400 mb-2">Connected Cameras</h4>
                <div className="space-y-2">
                  {status.cameras.map((camera) => (
                    <div
                      key={camera.id}
                      className="p-3 bg-white/5 rounded-xl flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <Camera className="w-5 h-5 text-cyan-400" />
                        <div>
                          <p className="text-white font-medium">{camera.name}</p>
                          <p className="text-xs text-gray-400">
                            {camera.type} • Battery: {camera.battery}
                          </p>
                        </div>
                      </div>
                      <div className={`w-2 h-2 rounded-full ${camera.armed ? 'bg-green-400' : 'bg-gray-500'}`} />
                    </div>
                  ))}
                </div>
              </div>

              {/* Disconnect */}
              <button
                onClick={handleDisconnect}
                disabled={loading}
                className="w-full py-2 text-red-400 hover:bg-red-500/10 rounded-xl transition-colors text-sm"
              >
                {loading ? 'Disconnecting...' : 'Disconnect Camera'}
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/10">
          <p className="text-xs text-gray-500 text-center">
            {step === 'connected'
              ? 'Fridge state updates automatically when door opens'
              : 'Connect your Blink camera for automatic fridge monitoring'}
          </p>
        </div>
      </div>
    </div>
  )
}

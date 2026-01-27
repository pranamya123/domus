/**
 * Debug Panel Component
 * For development and testing purposes
 */

import { useState } from 'react'
import {
  Terminal,
  Wifi,
  Database,
  RefreshCw,
  CheckCircle,
  XCircle,
  Loader2,
} from 'lucide-react'
import { api } from '../services/api'
import { useStore } from '../store/useStore'
import { useAuth } from '../providers/AuthProvider'

export default function DebugPanel() {
  const [healthStatus, setHealthStatus] = useState<'unknown' | 'healthy' | 'unhealthy'>('unknown')
  const [isChecking, setIsChecking] = useState(false)
  const [logs, setLogs] = useState<string[]>([])

  const { appState, isHardwareLinked, device, inventory, chatMessages, notifications } = useStore()
  const { user } = useAuth()

  const addLog = (message: string) => {
    const timestamp = new Date().toLocaleTimeString()
    setLogs((prev) => [...prev, `[${timestamp}] ${message}`].slice(-50))
  }

  const checkHealth = async () => {
    setIsChecking(true)
    addLog('Checking API health...')

    try {
      const result = await api.healthCheck()
      setHealthStatus(result.status === 'healthy' ? 'healthy' : 'unhealthy')
      addLog(`Health check: ${result.status}`)
    } catch (error) {
      setHealthStatus('unhealthy')
      addLog(`Health check failed: ${error}`)
    } finally {
      setIsChecking(false)
    }
  }

  const clearLogs = () => {
    setLogs([])
    addLog('Logs cleared')
  }

  return (
    <div className="h-full overflow-y-auto p-4 space-y-4">
      <h2 className="text-lg font-medium text-white flex items-center gap-2">
        <Terminal className="w-5 h-5" />
        Debug Panel
      </h2>

      {/* System Status */}
      <div className="glass rounded-xl p-4 space-y-3">
        <h3 className="text-sm font-medium text-gray-400">System Status</h3>

        <div className="grid grid-cols-2 gap-3">
          <div className="bg-white/5 rounded-lg p-3">
            <p className="text-xs text-gray-500">App State</p>
            <p className="text-sm text-white font-mono">{appState}</p>
          </div>
          <div className="bg-white/5 rounded-lg p-3">
            <p className="text-xs text-gray-500">Hardware</p>
            <p className={`text-sm font-mono ${isHardwareLinked ? 'text-green-400' : 'text-gray-400'}`}>
              {isHardwareLinked ? 'Connected' : 'Not Connected'}
            </p>
          </div>
          <div className="bg-white/5 rounded-lg p-3">
            <p className="text-xs text-gray-500">API Health</p>
            <div className="flex items-center gap-2">
              {healthStatus === 'unknown' ? (
                <span className="text-gray-400 text-sm">Unknown</span>
              ) : healthStatus === 'healthy' ? (
                <>
                  <CheckCircle className="w-4 h-4 text-green-400" />
                  <span className="text-green-400 text-sm">Healthy</span>
                </>
              ) : (
                <>
                  <XCircle className="w-4 h-4 text-red-400" />
                  <span className="text-red-400 text-sm">Unhealthy</span>
                </>
              )}
            </div>
          </div>
          <div className="bg-white/5 rounded-lg p-3">
            <button
              onClick={checkHealth}
              disabled={isChecking}
              className="flex items-center gap-2 text-sm text-domus-primary hover:text-domus-primary/80 disabled:opacity-50"
            >
              {isChecking ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <RefreshCw className="w-4 h-4" />
              )}
              Check Health
            </button>
          </div>
        </div>
      </div>

      {/* User Info */}
      <div className="glass rounded-xl p-4 space-y-3">
        <h3 className="text-sm font-medium text-gray-400">User Context</h3>
        <div className="bg-white/5 rounded-lg p-3 font-mono text-xs text-gray-300 overflow-x-auto">
          <pre>{JSON.stringify(user, null, 2)}</pre>
        </div>
      </div>

      {/* Device Info */}
      <div className="glass rounded-xl p-4 space-y-3">
        <h3 className="text-sm font-medium text-gray-400 flex items-center gap-2">
          <Wifi className="w-4 h-4" />
          Device State
        </h3>
        <div className="bg-white/5 rounded-lg p-3 font-mono text-xs text-gray-300 overflow-x-auto">
          <pre>{JSON.stringify(device, null, 2)}</pre>
        </div>
      </div>

      {/* Store State */}
      <div className="glass rounded-xl p-4 space-y-3">
        <h3 className="text-sm font-medium text-gray-400 flex items-center gap-2">
          <Database className="w-4 h-4" />
          Store State
        </h3>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="bg-white/5 rounded-lg p-3">
            <p className="text-2xl font-bold text-white">{chatMessages.length}</p>
            <p className="text-xs text-gray-500">Messages</p>
          </div>
          <div className="bg-white/5 rounded-lg p-3">
            <p className="text-2xl font-bold text-white">{inventory.length}</p>
            <p className="text-xs text-gray-500">Inventory</p>
          </div>
          <div className="bg-white/5 rounded-lg p-3">
            <p className="text-2xl font-bold text-white">{notifications.length}</p>
            <p className="text-xs text-gray-500">Notifications</p>
          </div>
        </div>
      </div>

      {/* Debug Logs */}
      <div className="glass rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-400">Debug Logs</h3>
          <button
            onClick={clearLogs}
            className="text-xs text-gray-500 hover:text-gray-400"
          >
            Clear
          </button>
        </div>
        <div className="bg-black/30 rounded-lg p-3 h-40 overflow-y-auto font-mono text-xs">
          {logs.length === 0 ? (
            <p className="text-gray-600">No logs yet...</p>
          ) : (
            logs.map((log, i) => (
              <p key={i} className="text-gray-400">{log}</p>
            ))
          )}
        </div>
      </div>

      {/* Version Info */}
      <div className="text-center text-xs text-gray-600">
        <p>Domus v0.1.0 | Phase 1 Development</p>
        <p>Server: {window.location.origin}</p>
      </div>
    </div>
  )
}

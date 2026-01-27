/**
 * Main application layout
 */

import { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Home, Bell, Settings, LogOut, Refrigerator } from 'lucide-react'
import { useAuth } from '../providers/AuthProvider'
import { useStore } from '../store/useStore'

interface LayoutProps {
  children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
  const { user, logout } = useAuth()
  const { unreadCount, appState, isHardwareLinked } = useStore()

  const getStatusColor = () => {
    switch (appState) {
      case 'CONNECTED_IDLE':
        return 'bg-green-500'
      case 'CONNECTED_SCANNING':
      case 'PROCESSING':
        return 'bg-yellow-500 animate-pulse'
      case 'ERROR':
        return 'bg-red-500'
      default:
        return 'bg-gray-500'
    }
  }

  return (
    <div className="min-h-screen bg-domus-dark-200 flex flex-col">
      {/* Header */}
      <header className="bg-domus-dark-100 border-b border-white/10 px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Refrigerator className="w-8 h-8 text-domus-primary" />
          <div>
            <h1 className="text-xl font-semibold text-white">Domus</h1>
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span className={`w-2 h-2 rounded-full ${getStatusColor()}`} />
              <span>
                {appState === 'CONNECTED_IDLE' ? 'Connected' :
                 appState === 'PROCESSING' ? 'Processing...' :
                 appState === 'CONNECTED_SCANNING' ? 'Scanning...' :
                 appState === 'ERROR' ? 'Error' : 'Disconnected'}
              </span>
              {isHardwareLinked && (
                <span className="text-domus-secondary">• Camera Online</span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {/* Notifications */}
          <button className="relative p-2 hover:bg-white/5 rounded-lg transition-colors">
            <Bell className="w-5 h-5 text-gray-400" />
            {unreadCount > 0 && (
              <span className="absolute -top-1 -right-1 bg-domus-danger text-white text-xs w-5 h-5 rounded-full flex items-center justify-center">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>

          {/* User menu */}
          <div className="flex items-center gap-3">
            <div className="text-right hidden sm:block">
              <p className="text-sm font-medium text-white">{user?.name}</p>
              <p className="text-xs text-gray-400">{user?.email}</p>
            </div>
            <button
              onClick={logout}
              className="p-2 hover:bg-white/5 rounded-lg transition-colors"
              title="Logout"
            >
              <LogOut className="w-5 h-5 text-gray-400" />
            </button>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 overflow-hidden">
        {children}
      </main>

      {/* Mobile bottom nav */}
      <nav className="sm:hidden bg-domus-dark-100 border-t border-white/10 px-4 py-2 flex justify-around">
        <Link
          to="/"
          className="flex flex-col items-center gap-1 p-2 text-domus-primary"
        >
          <Home className="w-5 h-5" />
          <span className="text-xs">Home</span>
        </Link>
        <button className="flex flex-col items-center gap-1 p-2 text-gray-400">
          <Bell className="w-5 h-5" />
          <span className="text-xs">Alerts</span>
        </button>
        <button className="flex flex-col items-center gap-1 p-2 text-gray-400">
          <Settings className="w-5 h-5" />
          <span className="text-xs">Settings</span>
        </button>
      </nav>
    </div>
  )
}

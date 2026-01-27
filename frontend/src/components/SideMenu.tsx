import { X, Camera, Bell, LogIn, LogOut, User, Calendar, Zap, Tag, ShoppingCart, Video } from 'lucide-react'
import { useStore } from '../store/useStore'

interface SideMenuProps {
  isOpen: boolean
  onClose: () => void
  onCameraClick: () => void
  onNotificationsClick: () => void
  onAlertsClick: () => void
  onBlinkSetupClick: () => void
  onSignInClick: () => void
  onSignOut: () => void
  user: { name: string; email: string } | null
}

export default function SideMenu({
  isOpen,
  onClose,
  onCameraClick,
  onNotificationsClick,
  onAlertsClick,
  onBlinkSetupClick,
  onSignInClick,
  onSignOut,
  user
}: SideMenuProps) {
  const { blinkConnected, blinkMonitoring } = useStore()

  if (!isOpen) return null

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/50 z-40"
        onClick={onClose}
      />

      {/* Menu Panel */}
      <div className="fixed inset-y-0 left-0 w-72 bg-[#171717] z-50 flex flex-col animate-slide-in-left">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h2 className="text-lg font-semibold text-white">Menu</h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Camera Status - Always visible at top */}
        <div className="p-4 border-b border-white/10">
          {blinkConnected ? (
            <div className="flex items-center gap-3">
              <div className="relative">
                <Video className="w-5 h-5 text-green-400" />
                <div className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 bg-green-500 rounded-full border-2 border-[#171717]" />
              </div>
              <div className="flex-1">
                <p className="text-white font-medium text-sm">Camera Connected</p>
                {blinkMonitoring && (
                  <p className="text-xs text-green-400">Auto-monitoring active</p>
                )}
              </div>
              <button
                onClick={onBlinkSetupClick}
                className="text-xs text-gray-400 hover:text-white"
              >
                Settings
              </button>
            </div>
          ) : (
            <button
              onClick={onBlinkSetupClick}
              className="w-full flex items-center gap-3 p-3 bg-cyan-500/10 hover:bg-cyan-500/20 border border-cyan-500/30 rounded-xl transition-colors"
            >
              <Video className="w-5 h-5 text-cyan-400" />
              <div className="text-left">
                <p className="text-white font-medium text-sm">Connect Camera</p>
                <p className="text-xs text-gray-400">Auto-capture on door open</p>
              </div>
            </button>
          )}
        </div>

        {/* User Section */}
        {user ? (
          <div className="p-4 border-b border-white/10">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-cyan-400 to-blue-500 rounded-full flex items-center justify-center">
                <User className="w-5 h-5 text-white" />
              </div>
              <div>
                <p className="text-white font-medium">{user.name}</p>
                <p className="text-sm text-gray-400">{user.email}</p>
              </div>
            </div>
            <div className="mt-3 flex items-center gap-2 text-sm text-green-400">
              <Calendar className="w-4 h-4" />
              <span>Calendar synced</span>
            </div>
          </div>
        ) : (
          <div className="p-4 border-b border-white/10">
            <p className="text-sm text-gray-400 mb-3">
              Sign in to sync with Google Calendar
            </p>
            <button
              onClick={onSignInClick}
              className="w-full flex items-center justify-center gap-2 bg-white text-black font-medium py-2.5 px-4 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <LogIn className="w-4 h-4" />
              Sign In
            </button>
          </div>
        )}

        {/* Menu Items */}
        <nav className="flex-1 p-2">
          <button
            onClick={onCameraClick}
            className="w-full flex items-center gap-3 px-4 py-3 text-gray-300 hover:bg-white/5 rounded-lg transition-colors"
          >
            <Camera className="w-5 h-5" />
            <span>Manual Scan</span>
          </button>

          <button
            onClick={onAlertsClick}
            className="w-full flex items-center gap-3 px-4 py-3 text-gray-300 hover:bg-white/5 rounded-lg transition-colors"
          >
            <Zap className="w-5 h-5 text-cyan-400" />
            <span>Smart Alerts</span>
            <span className="ml-auto bg-cyan-500/20 text-cyan-400 text-xs px-2 py-0.5 rounded-full">New</span>
          </button>

          <button
            onClick={onNotificationsClick}
            className="w-full flex items-center gap-3 px-4 py-3 text-gray-300 hover:bg-white/5 rounded-lg transition-colors"
          >
            <Bell className="w-5 h-5" />
            <span>Notifications</span>
          </button>

          <div className="my-2 border-t border-white/10" />

          <p className="px-4 py-2 text-xs text-gray-500 uppercase tracking-wider">Features</p>

          <div className="px-4 py-2 text-sm text-gray-400">
            <div className="flex items-center gap-2 mb-2">
              <Calendar className="w-4 h-4 text-blue-400" />
              <span>Calendar meal planning</span>
            </div>
            <div className="flex items-center gap-2 mb-2">
              <Tag className="w-4 h-4 text-green-400" />
              <span>Store deal alerts</span>
            </div>
            <div className="flex items-center gap-2">
              <ShoppingCart className="w-4 h-4 text-orange-400" />
              <span>Instacart ordering</span>
            </div>
          </div>
        </nav>

        {/* Sign Out */}
        {user && (
          <div className="p-4 border-t border-white/10">
            <button
              onClick={onSignOut}
              className="w-full flex items-center gap-3 px-4 py-3 text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
            >
              <LogOut className="w-5 h-5" />
              <span>Sign Out</span>
            </button>
          </div>
        )}
      </div>
    </>
  )
}

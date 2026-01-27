/**
 * Main dashboard page
 */

import { useEffect, useState } from 'react'
import ChatInterface from '../components/ChatInterface'
import CameraView from '../components/CameraView'
import NotificationInbox from '../components/NotificationInbox'
import DebugPanel from '../components/DebugPanel'
import { useStore } from '../store/useStore'
import { api } from '../services/api'
import { useAuth } from '../providers/AuthProvider'
import { MessageSquare, Camera, Bell, Bug } from 'lucide-react'

type Tab = 'chat' | 'camera' | 'notifications' | 'debug'

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<Tab>('chat')
  const { setAppState, setNotifications, setDevice, unreadCount } = useStore()
  const { user } = useAuth()

  // Initialize on mount
  useEffect(() => {
    const init = async () => {
      try {
        setAppState('CONNECTED_IDLE')

        // Load notifications
        const notifData = await api.getNotifications()
        setNotifications(notifData.notifications)

        // Load device status
        if (user?.household_id) {
          const deviceData = await api.getDeviceStatus(user.household_id)
          setDevice(deviceData)
        }
      } catch (error) {
        console.error('Init error:', error)
        setAppState('ERROR')
      }
    }

    init()
  }, [user, setAppState, setNotifications, setDevice])

  const tabs = [
    { id: 'chat' as Tab, label: 'Chat', icon: MessageSquare },
    { id: 'camera' as Tab, label: 'Scan', icon: Camera },
    { id: 'notifications' as Tab, label: 'Alerts', icon: Bell, badge: unreadCount },
    { id: 'debug' as Tab, label: 'Debug', icon: Bug },
  ]

  return (
    <div className="h-full flex flex-col">
      {/* Tab bar */}
      <div className="bg-domus-dark-100 border-b border-white/10 px-4">
        <div className="flex gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors relative
                ${activeTab === tab.id
                  ? 'text-domus-primary border-b-2 border-domus-primary'
                  : 'text-gray-400 hover:text-white'}
              `}
            >
              <tab.icon className="w-4 h-4" />
              <span className="hidden sm:inline">{tab.label}</span>
              {tab.badge && tab.badge > 0 && (
                <span className="absolute -top-1 -right-1 bg-domus-danger text-white text-xs w-5 h-5 rounded-full flex items-center justify-center">
                  {tab.badge > 9 ? '9+' : tab.badge}
                </span>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'chat' && <ChatInterface />}
        {activeTab === 'camera' && <CameraView />}
        {activeTab === 'notifications' && <NotificationInbox />}
        {activeTab === 'debug' && <DebugPanel />}
      </div>
    </div>
  )
}

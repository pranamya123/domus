/**
 * Notification Inbox Component
 * Displays and manages notifications
 */

import { useEffect, useState } from 'react'
import {
  Bell,
  AlertTriangle,
  ShoppingCart,
  Calendar,
  Wifi,
  Check,
  CheckCheck,
  Loader2,
} from 'lucide-react'
import { api } from '../services/api'
import { useStore } from '../store/useStore'
import type { Notification } from '../types'
import { formatDistanceToNow } from 'date-fns'

const notificationIcons: Record<string, typeof Bell> = {
  perishable_expiry: AlertTriangle,
  procurement_required: ShoppingCart,
  calendar_event_ingredient_missing: Calendar,
  hardware_disconnected: Wifi,
}

const severityColors: Record<string, string> = {
  low: 'text-gray-400',
  medium: 'text-yellow-400',
  high: 'text-orange-400',
  urgent: 'text-red-400',
}

export default function NotificationInbox() {
  const [isLoading, setIsLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const { notifications, setNotifications, markNotificationRead, markAllRead, unreadCount } = useStore()

  // Load notifications
  useEffect(() => {
    const loadNotifications = async () => {
      setIsLoading(true)
      try {
        const data = await api.getNotifications(filter === 'unread')
        setNotifications(data.notifications)
      } catch (error) {
        console.error('Failed to load notifications:', error)
      } finally {
        setIsLoading(false)
      }
    }

    loadNotifications()
  }, [filter, setNotifications])

  const handleMarkRead = async (notification: Notification) => {
    if (notification.is_read) return

    try {
      await api.markNotificationRead(notification.id)
      markNotificationRead(notification.id)
    } catch (error) {
      console.error('Failed to mark notification read:', error)
    }
  }

  const handleMarkAllRead = async () => {
    try {
      await api.markAllNotificationsRead()
      markAllRead()
    } catch (error) {
      console.error('Failed to mark all notifications read:', error)
    }
  }

  const formatTimestamp = (timestamp: string) => {
    try {
      return formatDistanceToNow(new Date(timestamp), { addSuffix: true })
    } catch {
      return timestamp
    }
  }

  const filteredNotifications = filter === 'unread'
    ? notifications.filter((n) => !n.is_read)
    : notifications

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="p-4 border-b border-white/10 bg-domus-dark-100">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-medium text-white">Notifications</h2>
          {unreadCount > 0 && (
            <button
              onClick={handleMarkAllRead}
              className="text-sm text-domus-primary hover:text-domus-primary/80 flex items-center gap-1"
            >
              <CheckCheck className="w-4 h-4" />
              Mark all read
            </button>
          )}
        </div>

        {/* Filter tabs */}
        <div className="flex gap-2">
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors ${
              filter === 'all'
                ? 'bg-domus-primary text-white'
                : 'bg-white/5 text-gray-400 hover:bg-white/10'
            }`}
          >
            All
          </button>
          <button
            onClick={() => setFilter('unread')}
            className={`px-3 py-1.5 rounded-lg text-sm transition-colors flex items-center gap-2 ${
              filter === 'unread'
                ? 'bg-domus-primary text-white'
                : 'bg-white/5 text-gray-400 hover:bg-white/10'
            }`}
          >
            Unread
            {unreadCount > 0 && (
              <span className="bg-white/20 px-1.5 py-0.5 rounded text-xs">
                {unreadCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Notification list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-8 h-8 text-domus-primary animate-spin" />
          </div>
        ) : filteredNotifications.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-gray-500">
            <Bell className="w-12 h-12 mb-4 opacity-50" />
            <p>No notifications</p>
            {filter === 'unread' && (
              <p className="text-sm mt-1">You're all caught up!</p>
            )}
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {filteredNotifications.map((notification) => {
              const Icon = notificationIcons[notification.notification_type] || Bell
              const severityColor = severityColors[notification.severity] || 'text-gray-400'

              return (
                <div
                  key={notification.id}
                  onClick={() => handleMarkRead(notification)}
                  className={`p-4 hover:bg-white/5 cursor-pointer transition-colors ${
                    !notification.is_read ? 'bg-domus-primary/5' : ''
                  }`}
                >
                  <div className="flex gap-3">
                    <div
                      className={`w-10 h-10 rounded-xl flex items-center justify-center ${
                        !notification.is_read ? 'bg-domus-primary/10' : 'bg-white/5'
                      }`}
                    >
                      <Icon className={`w-5 h-5 ${severityColor}`} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <h3
                          className={`font-medium truncate ${
                            notification.is_read ? 'text-gray-400' : 'text-white'
                          }`}
                        >
                          {notification.title}
                        </h3>
                        {!notification.is_read && (
                          <span className="w-2 h-2 bg-domus-primary rounded-full flex-shrink-0 mt-2" />
                        )}
                      </div>
                      <p
                        className={`text-sm mt-1 line-clamp-2 ${
                          notification.is_read ? 'text-gray-500' : 'text-gray-400'
                        }`}
                      >
                        {notification.message}
                      </p>
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-xs text-gray-500">
                          {formatTimestamp(notification.created_at)}
                        </span>
                        {notification.is_read && notification.read_at && (
                          <span className="flex items-center gap-1 text-xs text-gray-600">
                            <Check className="w-3 h-3" />
                            Read
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

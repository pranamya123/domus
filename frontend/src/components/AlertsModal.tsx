import { useState, useEffect } from 'react'
import { X, Bell, Calendar, Clock, Tag, ShoppingCart, Check, Loader2, AlertTriangle } from 'lucide-react'
import { fetchProactiveAlerts, createInstacartOrder, approveOrder, showLocalNotification, requestNotificationPermission, subscribeToPush } from '../utils/notifications'

interface Alert {
  type: string
  alert_id: string
  message: string
  action?: {
    type: string
    items?: string[]
  }
  event_name?: string
  days_until?: number
  item_name?: string
  hours_until?: number
  store?: string
  savings?: number
}

interface AlertsModalProps {
  isOpen: boolean
  onClose: () => void
}

export default function AlertsModal({ isOpen, onClose }: AlertsModalProps) {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [loading, setLoading] = useState(true)
  const [ordering, setOrdering] = useState<string | null>(null)
  const [notificationsEnabled, setNotificationsEnabled] = useState(false)

  useEffect(() => {
    if (isOpen) {
      loadAlerts()
      checkNotificationStatus()
    }
  }, [isOpen])

  const loadAlerts = async () => {
    setLoading(true)
    try {
      const data = await fetchProactiveAlerts()
      setAlerts(data.alerts || [])
    } catch (error) {
      console.error('Failed to load alerts:', error)
    } finally {
      setLoading(false)
    }
  }

  const checkNotificationStatus = () => {
    if ('Notification' in window) {
      setNotificationsEnabled(Notification.permission === 'granted')
    }
  }

  const enableNotifications = async () => {
    const permission = await requestNotificationPermission()
    if (permission === 'granted') {
      await subscribeToPush()
      setNotificationsEnabled(true)
      showLocalNotification(
        'Notifications Enabled',
        'You will now receive alerts from Domus'
      )
    }
  }

  const handleOrder = async (alert: Alert) => {
    if (!alert.action?.items) return

    setOrdering(alert.alert_id)
    try {
      const order = await createInstacartOrder(alert.action.items)

      // Auto-approve for demo
      await approveOrder(order.order_id)

      // Show success notification
      showLocalNotification(
        'Order Placed!',
        `${alert.action.items.join(', ')} will be delivered in ~2 hours`
      )

      // Remove alert from list
      setAlerts(prev => prev.filter(a => a.alert_id !== alert.alert_id))
    } catch (error) {
      console.error('Order failed:', error)
    } finally {
      setOrdering(null)
    }
  }

  const getAlertIcon = (type: string) => {
    switch (type) {
      case 'calendar_ingredients':
        return <Calendar className="w-5 h-5 text-blue-400" />
      case 'expiry_warning':
      case 'item_expired':
        return <Clock className="w-5 h-5 text-orange-400" />
      case 'bulk_buy_deal':
        return <Tag className="w-5 h-5 text-green-400" />
      default:
        return <Bell className="w-5 h-5 text-cyan-400" />
    }
  }

  const getAlertColor = (type: string) => {
    switch (type) {
      case 'item_expired':
        return 'border-red-500/30 bg-red-500/10'
      case 'expiry_warning':
        return 'border-orange-500/30 bg-orange-500/10'
      case 'calendar_ingredients':
        return 'border-blue-500/30 bg-blue-500/10'
      case 'bulk_buy_deal':
        return 'border-green-500/30 bg-green-500/10'
      default:
        return 'border-white/10 bg-white/5'
    }
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
      <div className="bg-[#212121] rounded-2xl w-full max-w-md max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div className="flex items-center gap-2">
            <Bell className="w-5 h-5 text-cyan-400" />
            <h2 className="text-lg font-semibold text-white">Smart Alerts</h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Notification Permission Banner */}
        {!notificationsEnabled && (
          <div className="p-3 bg-cyan-500/10 border-b border-cyan-500/20">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Bell className="w-4 h-4 text-cyan-400" />
                <span className="text-sm text-cyan-300">Enable push notifications</span>
              </div>
              <button
                onClick={enableNotifications}
                className="px-3 py-1 bg-cyan-500 text-white text-sm rounded-lg hover:bg-cyan-600 transition-colors"
              >
                Enable
              </button>
            </div>
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-cyan-400 animate-spin" />
            </div>
          ) : alerts.length === 0 ? (
            <div className="text-center py-12">
              <Bell className="w-12 h-12 text-gray-600 mx-auto mb-3" />
              <p className="text-gray-400">No alerts right now</p>
              <p className="text-sm text-gray-500 mt-1">
                We'll notify you about expiring items, deals, and calendar events
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              {alerts.map((alert) => (
                <div
                  key={alert.alert_id}
                  className={`p-4 rounded-xl border ${getAlertColor(alert.type)}`}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5">
                      {getAlertIcon(alert.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-white text-sm">{alert.message}</p>

                      {alert.type === 'bulk_buy_deal' && alert.savings && (
                        <p className="text-green-400 text-xs mt-1">
                          Save ${alert.savings.toFixed(2)} at {alert.store}
                        </p>
                      )}

                      {alert.action?.type === 'order_instacart' && alert.action.items && (
                        <button
                          onClick={() => handleOrder(alert)}
                          disabled={ordering === alert.alert_id}
                          className="mt-3 flex items-center gap-2 px-3 py-2 bg-cyan-500 hover:bg-cyan-600 disabled:bg-cyan-500/50 text-white text-sm rounded-lg transition-colors"
                        >
                          {ordering === alert.alert_id ? (
                            <>
                              <Loader2 className="w-4 h-4 animate-spin" />
                              Ordering...
                            </>
                          ) : (
                            <>
                              <ShoppingCart className="w-4 h-4" />
                              Order from Instacart
                            </>
                          )}
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/10">
          <p className="text-xs text-gray-500 text-center">
            Domus monitors your fridge and calendar to send proactive alerts
          </p>
        </div>
      </div>
    </div>
  )
}

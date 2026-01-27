import { useState, useEffect } from 'react'
import ChatPage from './pages/ChatPage'
import SideMenu from './components/SideMenu'
import CameraModal from './components/CameraModal'
import NotificationsModal from './components/NotificationsModal'
import SignInModal from './components/SignInModal'
import AlertsModal from './components/AlertsModal'
import BlinkSetupModal from './components/BlinkSetupModal'
import { useStore } from './store/useStore'

function App() {
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const [isCameraOpen, setIsCameraOpen] = useState(false)
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false)
  const [isSignInOpen, setIsSignInOpen] = useState(false)
  const [isAlertsOpen, setIsAlertsOpen] = useState(false)
  const [isBlinkSetupOpen, setIsBlinkSetupOpen] = useState(false)
  const [user, setUser] = useState<{ name: string; email: string } | null>(null)

  const { setBlinkStatus } = useStore()

  // Check Blink status on app load
  useEffect(() => {
    const checkBlinkStatus = async () => {
      try {
        const response = await fetch('/api/blink/status')
        const data = await response.json()
        setBlinkStatus(data.initialized, data.monitoring)
      } catch (err) {
        // Blink not connected - that's okay
        setBlinkStatus(false, false)
      }
    }
    checkBlinkStatus()
  }, [setBlinkStatus])

  const handleSignIn = (name: string, email: string) => {
    setUser({ name, email })
    setIsSignInOpen(false)
  }

  const handleSignOut = () => {
    setUser(null)
    setIsMenuOpen(false)
  }

  return (
    <div className="h-screen bg-[#212121] text-white overflow-hidden">
      {/* Main Chat Interface */}
      <ChatPage
        onMenuOpen={() => setIsMenuOpen(true)}
        onCameraOpen={() => setIsCameraOpen(true)}
        user={user}
      />

      {/* Side Menu */}
      <SideMenu
        isOpen={isMenuOpen}
        onClose={() => setIsMenuOpen(false)}
        onCameraClick={() => {
          setIsMenuOpen(false)
          setIsCameraOpen(true)
        }}
        onNotificationsClick={() => {
          setIsMenuOpen(false)
          setIsNotificationsOpen(true)
        }}
        onAlertsClick={() => {
          setIsMenuOpen(false)
          setIsAlertsOpen(true)
        }}
        onBlinkSetupClick={() => {
          setIsMenuOpen(false)
          setIsBlinkSetupOpen(true)
        }}
        onSignInClick={() => {
          setIsMenuOpen(false)
          setIsSignInOpen(true)
        }}
        onSignOut={handleSignOut}
        user={user}
      />

      {/* Camera Modal - Manual scan fallback */}
      <CameraModal
        isOpen={isCameraOpen}
        onClose={() => setIsCameraOpen(false)}
      />

      {/* Notifications Modal */}
      <NotificationsModal
        isOpen={isNotificationsOpen}
        onClose={() => setIsNotificationsOpen(false)}
      />

      {/* Sign In Modal */}
      <SignInModal
        isOpen={isSignInOpen}
        onClose={() => setIsSignInOpen(false)}
        onSignIn={handleSignIn}
      />

      {/* Smart Alerts Modal */}
      <AlertsModal
        isOpen={isAlertsOpen}
        onClose={() => setIsAlertsOpen(false)}
      />

      {/* Blink Camera Setup Modal */}
      <BlinkSetupModal
        isOpen={isBlinkSetupOpen}
        onClose={() => setIsBlinkSetupOpen(false)}
      />
    </div>
  )
}

export default App

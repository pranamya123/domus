/**
 * Login page
 */

import { useState } from 'react'
import { Refrigerator, Mail, User } from 'lucide-react'
import { useAuth } from '../providers/AuthProvider'

export default function LoginPage() {
  const { login, isLoading } = useAuth()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')

    if (!email || !name) {
      setError('Please fill in all fields')
      return
    }

    try {
      await login(email, name)
    } catch (err) {
      setError('Login failed. Please try again.')
      console.error('Login error:', err)
    }
  }

  return (
    <div className="min-h-screen bg-domus-dark-200 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-domus-primary/10 rounded-2xl mb-4">
            <Refrigerator className="w-8 h-8 text-domus-primary" />
          </div>
          <h1 className="text-3xl font-bold text-white">Domus</h1>
          <p className="text-gray-400 mt-2">Smart Fridge Assistant</p>
        </div>

        {/* Login form */}
        <div className="glass rounded-2xl p-6">
          <h2 className="text-xl font-semibold text-white mb-6">Welcome</h2>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-2">Name</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Your name"
                  className="w-full bg-domus-dark-200 border border-white/10 rounded-lg pl-10 pr-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-domus-primary transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-2">Email</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full bg-domus-dark-200 border border-white/10 rounded-lg pl-10 pr-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-domus-primary transition-colors"
                />
              </div>
            </div>

            {error && (
              <p className="text-domus-danger text-sm">{error}</p>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full bg-domus-primary hover:bg-domus-primary/90 disabled:bg-domus-primary/50 text-white font-medium py-3 rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {isLoading ? (
                <>
                  <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  Signing in...
                </>
              ) : (
                'Sign In'
              )}
            </button>
          </form>

          <div className="mt-6 pt-6 border-t border-white/10">
            <p className="text-xs text-gray-500 text-center">
              This is a development login. In production, use Google OAuth.
            </p>
          </div>
        </div>

        {/* Features preview */}
        <div className="mt-8 grid grid-cols-3 gap-4 text-center">
          <div className="p-4">
            <div className="text-2xl mb-2">📷</div>
            <p className="text-xs text-gray-400">Auto-scan your fridge</p>
          </div>
          <div className="p-4">
            <div className="text-2xl mb-2">📅</div>
            <p className="text-xs text-gray-400">Track expiration dates</p>
          </div>
          <div className="p-4">
            <div className="text-2xl mb-2">🛒</div>
            <p className="text-xs text-gray-400">Smart shopping lists</p>
          </div>
        </div>
      </div>
    </div>
  )
}

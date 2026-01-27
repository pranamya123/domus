/**
 * Chat Interface Component
 * Handles conversation with Domus AI
 */

import { useState, useRef, useEffect } from 'react'
import { Send, Loader2, Refrigerator } from 'lucide-react'
import { api } from '../services/api'
import { useStore } from '../store/useStore'
import type { ChatMessage } from '../types'
import { v4 as uuidv4 } from 'uuid'

// Simple UUID generator since we removed the dependency
function generateId(): string {
  return Math.random().toString(36).substring(2) + Date.now().toString(36)
}

export default function ChatInterface() {
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const { chatMessages, addChatMessage, setAppState } = useStore()

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages])

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const handleSend = async () => {
    const message = input.trim()
    if (!message || isLoading) return

    // Add user message
    const userMessage: ChatMessage = {
      id: generateId(),
      role: 'user',
      content: message,
      timestamp: new Date().toISOString(),
    }
    addChatMessage(userMessage)
    setInput('')
    setIsLoading(true)
    setAppState('PROCESSING')

    try {
      const response = await api.sendMessage(message)

      // Add assistant response
      const assistantMessage: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: response.response,
        timestamp: new Date().toISOString(),
      }
      addChatMessage(assistantMessage)
    } catch (error) {
      console.error('Chat error:', error)
      const errorMessage: ChatMessage = {
        id: generateId(),
        role: 'assistant',
        content: 'Sorry, I encountered an error. Please try again.',
        timestamp: new Date().toISOString(),
      }
      addChatMessage(errorMessage)
    } finally {
      setIsLoading(false)
      setAppState('CONNECTED_IDLE')
    }
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const formatMessage = (content: string) => {
    // Simple markdown-like formatting
    return content
      .split('\n')
      .map((line, i) => {
        // Bold
        line = line.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        // Lists
        if (line.startsWith('- ')) {
          return `<li class="ml-4">${line.substring(2)}</li>`
        }
        return line
      })
      .join('<br/>')
  }

  return (
    <div className="h-full flex flex-col">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {chatMessages.length === 0 && (
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-domus-primary/10 rounded-2xl mb-4">
              <Refrigerator className="w-8 h-8 text-domus-primary" />
            </div>
            <h3 className="text-lg font-medium text-white mb-2">
              Hi! I'm Domus
            </h3>
            <p className="text-gray-400 max-w-sm mx-auto">
              I can help you manage your fridge inventory, track expiration dates,
              and suggest meals. Try asking:
            </p>
            <div className="mt-4 flex flex-wrap gap-2 justify-center">
              {[
                "What's in my fridge?",
                "What's expiring soon?",
                "What can I cook?",
              ].map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => {
                    setInput(suggestion)
                    inputRef.current?.focus()
                  }}
                  className="px-3 py-1.5 bg-white/5 hover:bg-white/10 rounded-full text-sm text-gray-300 transition-colors"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}

        {chatMessages.map((message) => (
          <div
            key={message.id}
            className={`flex animate-slide-in ${
              message.role === 'user' ? 'justify-end' : 'justify-start'
            }`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                message.role === 'user'
                  ? 'bg-domus-primary text-white'
                  : 'bg-domus-dark-100 text-gray-100'
              }`}
            >
              <div
                className="text-sm whitespace-pre-wrap"
                dangerouslySetInnerHTML={{ __html: formatMessage(message.content) }}
              />
              <p
                className={`text-xs mt-1 ${
                  message.role === 'user' ? 'text-blue-200' : 'text-gray-500'
                }`}
              >
                {new Date(message.timestamp).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </p>
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start animate-slide-in">
            <div className="bg-domus-dark-100 rounded-2xl px-4 py-3">
              <div className="flex items-center gap-2 text-gray-400">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span className="text-sm">Thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="p-4 border-t border-white/10 bg-domus-dark-100">
        <div className="flex gap-2">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about your fridge..."
            disabled={isLoading}
            className="flex-1 bg-domus-dark-200 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-domus-primary transition-colors disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="bg-domus-primary hover:bg-domus-primary/90 disabled:bg-domus-primary/30 text-white p-3 rounded-xl transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </div>
    </div>
  )
}

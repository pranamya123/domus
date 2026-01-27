/**
 * API service for Domus backend communication
 */

import axios, { AxiosError, AxiosInstance } from 'axios'
import type {
  User,
  AuthToken,
  ChatResponse,
  Notification,
  UploadResponse,
  Device,
} from '../types'

const API_BASE_URL = '/api'

class ApiService {
  private client: AxiosInstance
  private token: string | null = null

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Add token to requests
    this.client.interceptors.request.use((config) => {
      if (this.token) {
        config.headers.Authorization = `Bearer ${this.token}`
      }
      return config
    })

    // Handle errors
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          // Clear token and redirect to login
          this.setToken(null)
          window.location.href = '/login'
        }
        return Promise.reject(error)
      }
    )
  }

  setToken(token: string | null) {
    this.token = token
    if (token) {
      localStorage.setItem('domus_token', token)
    } else {
      localStorage.removeItem('domus_token')
    }
  }

  getToken(): string | null {
    if (!this.token) {
      this.token = localStorage.getItem('domus_token')
    }
    return this.token
  }

  // Auth endpoints
  async login(email: string, name: string): Promise<{ user: User; token: AuthToken }> {
    const response = await this.client.post('/auth/login', { email, name })
    const { user, token } = response.data
    this.setToken(token.access_token)
    return { user, token }
  }

  async logout(): Promise<void> {
    await this.client.post('/auth/logout')
    this.setToken(null)
  }

  async getCurrentUser(): Promise<User> {
    const response = await this.client.get('/auth/me')
    return response.data
  }

  // Chat endpoints
  async sendMessage(message: string): Promise<ChatResponse> {
    const response = await this.client.post('/chat/message', { message })
    return response.data
  }

  async getChatHistory(): Promise<{ messages: Array<{ role: string; content: string; timestamp: string }> }> {
    const response = await this.client.get('/chat/history')
    return response.data
  }

  async clearChatHistory(): Promise<void> {
    await this.client.delete('/chat/history')
  }

  // Upload endpoints
  async uploadImage(file: File, overrideIot: boolean = false): Promise<UploadResponse> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await this.client.post(
      `/upload/image?override_iot=${overrideIot}`,
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      }
    )
    return response.data
  }

  async validateImage(file: File): Promise<{ is_valid: boolean; confidence: number; reason?: string }> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await this.client.post('/upload/validate', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
    return response.data
  }

  // Notification endpoints
  async getNotifications(unreadOnly: boolean = false): Promise<{
    notifications: Notification[]
    total: number
    unread_count: number
  }> {
    const response = await this.client.get('/notifications/', {
      params: { unread_only: unreadOnly },
    })
    return response.data
  }

  async markNotificationRead(notificationId: string): Promise<void> {
    await this.client.post(`/notifications/read/${notificationId}`)
  }

  async markAllNotificationsRead(): Promise<{ marked_count: number }> {
    const response = await this.client.post('/notifications/read-all')
    return response.data
  }

  // Device endpoints
  async getDeviceStatus(householdId: string): Promise<Device> {
    const response = await this.client.get(`/ingest/device/${householdId}/status`)
    return response.data
  }

  // Health check
  async healthCheck(): Promise<{ status: string }> {
    const response = await this.client.get('/health')
    return response.data
  }
}

export const api = new ApiService()
export default api

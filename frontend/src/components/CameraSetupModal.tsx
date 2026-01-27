import { useState, useEffect } from 'react'
import { X, Camera, Wifi, Check, Copy, RefreshCw, AlertCircle, Smartphone } from 'lucide-react'

interface CameraSetupModalProps {
  isOpen: boolean
  onClose: () => void
}

interface DeviceStatus {
  device_id: string
  status: string
  last_seen: string | null
  is_simulated: boolean
}

export default function CameraSetupModal({ isOpen, onClose }: CameraSetupModalProps) {
  const [step, setStep] = useState(1)
  const [deviceToken, setDeviceToken] = useState('')
  const [apiEndpoint, setApiEndpoint] = useState('')
  const [deviceStatus, setDeviceStatus] = useState<DeviceStatus | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)

  const householdId = 'anonymous_household' // In production, get from auth

  useEffect(() => {
    if (isOpen) {
      // Generate device token (in production, this comes from server)
      const token = `domus_${Math.random().toString(36).substring(2, 15)}`
      setDeviceToken(token)

      // Set API endpoint based on current host
      const host = window.location.hostname
      const endpoint = `http://${host}:8000/api/ingest/iot?household_id=${householdId}`
      setApiEndpoint(endpoint)

      // Check device status
      checkDeviceStatus()
    }
  }, [isOpen])

  const checkDeviceStatus = async () => {
    try {
      const response = await fetch(`/api/ingest/device/${householdId}/status`)
      const data = await response.json()
      setDeviceStatus(data)
    } catch (error) {
      console.error('Failed to check device status:', error)
    }
  }

  const copyToClipboard = (text: string, field: string) => {
    navigator.clipboard.writeText(text)
    setCopied(field)
    setTimeout(() => setCopied(null), 2000)
  }

  const testConnection = async () => {
    setTesting(true)
    try {
      // Simulate a test by checking status
      await new Promise(resolve => setTimeout(resolve, 2000))
      await checkDeviceStatus()
    } finally {
      setTesting(false)
    }
  }

  const getArduinoCode = () => `
// Domus Fridge Camera - ESP32-CAM Code
#include <WiFi.h>
#include <HTTPClient.h>
#include "esp_camera.h"

const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* serverUrl = "${apiEndpoint}";
const char* deviceToken = "${deviceToken}";

// Door sensor pin
const int DOOR_PIN = 13;

void setup() {
  Serial.begin(115200);

  // Initialize camera
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_VGA;
  config.jpeg_quality = 12;
  config.fb_count = 1;

  esp_camera_init(&config);

  // Connect to WiFi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
  }

  // Setup door sensor
  pinMode(DOOR_PIN, INPUT_PULLUP);
}

void loop() {
  // Check if door is open
  if (digitalRead(DOOR_PIN) == HIGH) {
    delay(2000); // Wait for door to fully open
    captureAndSend();
  }
  delay(100);
}

void captureAndSend() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return;

  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Device-Token", deviceToken);

  int httpCode = http.POST(fb->buf, fb->len);

  esp_camera_fb_return(fb);
  http.end();
}
`

  const getRaspberryPiCode = () => `
#!/usr/bin/env python3
# Domus Fridge Camera - Raspberry Pi Code

import requests
import time
from picamera2 import Picamera2
import RPi.GPIO as GPIO

API_URL = "${apiEndpoint}"
DEVICE_TOKEN = "${deviceToken}"
DOOR_PIN = 17

# Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(DOOR_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

camera = Picamera2()
camera.configure(camera.create_still_configuration())

def capture_and_send():
    """Capture image and send to Domus"""
    camera.start()
    time.sleep(2)  # Let camera adjust

    image_data = camera.capture_array()
    camera.stop()

    # Convert to JPEG bytes
    import io
    from PIL import Image
    img = Image.fromarray(image_data)
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=85)
    buffer.seek(0)

    # Send to Domus
    response = requests.post(
        API_URL,
        files={'file': ('fridge.jpg', buffer, 'image/jpeg')},
        headers={'X-Device-Token': DEVICE_TOKEN}
    )
    print(f"Sent: {response.json()}")

def door_callback(channel):
    """Called when door opens"""
    time.sleep(2)  # Wait for door to open
    capture_and_send()

# Watch for door open
GPIO.add_event_detect(DOOR_PIN, GPIO.RISING,
                      callback=door_callback,
                      bouncetime=5000)

print("Domus camera ready. Waiting for door open...")
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    GPIO.cleanup()
`

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4">
      <div className="bg-[#212121] rounded-2xl w-full max-w-lg max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <div className="flex items-center gap-2">
            <Camera className="w-5 h-5 text-cyan-400" />
            <h2 className="text-lg font-semibold text-white">Setup Fridge Camera</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/10 rounded-lg">
            <X className="w-5 h-5 text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">
          {/* Status Banner */}
          <div className={`p-3 rounded-xl mb-4 flex items-center gap-3 ${
            deviceStatus?.status === 'online'
              ? 'bg-green-500/10 border border-green-500/30'
              : 'bg-yellow-500/10 border border-yellow-500/30'
          }`}>
            {deviceStatus?.status === 'online' ? (
              <>
                <Check className="w-5 h-5 text-green-400" />
                <div>
                  <p className="text-green-400 font-medium">Camera Connected</p>
                  <p className="text-xs text-gray-400">Last seen: {deviceStatus.last_seen || 'just now'}</p>
                </div>
              </>
            ) : (
              <>
                <Wifi className="w-5 h-5 text-yellow-400" />
                <div>
                  <p className="text-yellow-400 font-medium">Waiting for camera...</p>
                  <p className="text-xs text-gray-400">Follow the setup steps below</p>
                </div>
              </>
            )}
            <button onClick={checkDeviceStatus} className="ml-auto p-2 hover:bg-white/10 rounded-lg">
              <RefreshCw className="w-4 h-4 text-gray-400" />
            </button>
          </div>

          {/* Steps */}
          <div className="space-y-4">
            {/* Step 1: Camera Type */}
            <div className={`p-4 rounded-xl border ${step === 1 ? 'border-cyan-500/50 bg-cyan-500/5' : 'border-white/10'}`}>
              <div className="flex items-center gap-2 mb-3">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-sm font-bold ${
                  step >= 1 ? 'bg-cyan-500 text-white' : 'bg-white/10 text-gray-400'
                }`}>1</div>
                <h3 className="font-medium text-white">What camera do you have?</h3>
              </div>

              {step === 1 && (
                <div className="grid grid-cols-2 gap-3">
                  <button
                    onClick={() => setStep(2)}
                    className="p-4 rounded-xl border border-white/10 hover:border-cyan-500/50 hover:bg-cyan-500/5 transition-colors text-left"
                  >
                    <Smartphone className="w-6 h-6 text-cyan-400 mb-2" />
                    <p className="text-white font-medium">ESP32-CAM</p>
                    <p className="text-xs text-gray-400">Arduino compatible</p>
                  </button>
                  <button
                    onClick={() => setStep(2)}
                    className="p-4 rounded-xl border border-white/10 hover:border-cyan-500/50 hover:bg-cyan-500/5 transition-colors text-left"
                  >
                    <Camera className="w-6 h-6 text-green-400 mb-2" />
                    <p className="text-white font-medium">Raspberry Pi</p>
                    <p className="text-xs text-gray-400">With Pi Camera</p>
                  </button>
                </div>
              )}
            </div>

            {/* Step 2: Configuration */}
            <div className={`p-4 rounded-xl border ${step === 2 ? 'border-cyan-500/50 bg-cyan-500/5' : 'border-white/10'}`}>
              <div className="flex items-center gap-2 mb-3">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-sm font-bold ${
                  step >= 2 ? 'bg-cyan-500 text-white' : 'bg-white/10 text-gray-400'
                }`}>2</div>
                <h3 className="font-medium text-white">Configure your camera</h3>
              </div>

              {step >= 2 && (
                <div className="space-y-3">
                  {/* API Endpoint */}
                  <div>
                    <label className="text-xs text-gray-400 mb-1 block">API Endpoint</label>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 bg-black/30 text-cyan-400 text-xs p-2 rounded-lg overflow-x-auto">
                        {apiEndpoint}
                      </code>
                      <button
                        onClick={() => copyToClipboard(apiEndpoint, 'endpoint')}
                        className="p-2 hover:bg-white/10 rounded-lg"
                      >
                        {copied === 'endpoint' ? (
                          <Check className="w-4 h-4 text-green-400" />
                        ) : (
                          <Copy className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Device Token */}
                  <div>
                    <label className="text-xs text-gray-400 mb-1 block">Device Token</label>
                    <div className="flex items-center gap-2">
                      <code className="flex-1 bg-black/30 text-cyan-400 text-xs p-2 rounded-lg overflow-x-auto">
                        {deviceToken}
                      </code>
                      <button
                        onClick={() => copyToClipboard(deviceToken, 'token')}
                        className="p-2 hover:bg-white/10 rounded-lg"
                      >
                        {copied === 'token' ? (
                          <Check className="w-4 h-4 text-green-400" />
                        ) : (
                          <Copy className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                    </div>
                  </div>

                  <button
                    onClick={() => setStep(3)}
                    className="w-full py-2 bg-cyan-500 hover:bg-cyan-600 text-white rounded-lg transition-colors"
                  >
                    Next: Get Code
                  </button>
                </div>
              )}
            </div>

            {/* Step 3: Code */}
            <div className={`p-4 rounded-xl border ${step === 3 ? 'border-cyan-500/50 bg-cyan-500/5' : 'border-white/10'}`}>
              <div className="flex items-center gap-2 mb-3">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center text-sm font-bold ${
                  step >= 3 ? 'bg-cyan-500 text-white' : 'bg-white/10 text-gray-400'
                }`}>3</div>
                <h3 className="font-medium text-white">Upload code to your device</h3>
              </div>

              {step >= 3 && (
                <div className="space-y-3">
                  <div className="flex gap-2">
                    <button
                      onClick={() => copyToClipboard(getArduinoCode(), 'arduino')}
                      className="flex-1 py-2 px-3 bg-white/5 hover:bg-white/10 rounded-lg text-sm flex items-center justify-center gap-2"
                    >
                      {copied === 'arduino' ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                      ESP32 Code
                    </button>
                    <button
                      onClick={() => copyToClipboard(getRaspberryPiCode(), 'rpi')}
                      className="flex-1 py-2 px-3 bg-white/5 hover:bg-white/10 rounded-lg text-sm flex items-center justify-center gap-2"
                    >
                      {copied === 'rpi' ? <Check className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                      Raspberry Pi Code
                    </button>
                  </div>

                  <div className="p-3 bg-blue-500/10 border border-blue-500/30 rounded-xl">
                    <div className="flex items-start gap-2">
                      <AlertCircle className="w-4 h-4 text-blue-400 mt-0.5" />
                      <div className="text-xs text-blue-300">
                        <p className="font-medium mb-1">Setup Instructions:</p>
                        <ol className="list-decimal ml-4 space-y-1 text-blue-200">
                          <li>Replace YOUR_WIFI_SSID and YOUR_WIFI_PASSWORD</li>
                          <li>Upload code to your device</li>
                          <li>Connect door sensor to specified pin</li>
                          <li>Mount camera inside fridge</li>
                        </ol>
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={testConnection}
                    disabled={testing}
                    className="w-full py-2 bg-green-500 hover:bg-green-600 disabled:bg-green-500/50 text-white rounded-lg transition-colors flex items-center justify-center gap-2"
                  >
                    {testing ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        Testing Connection...
                      </>
                    ) : (
                      <>
                        <Wifi className="w-4 h-4" />
                        Test Connection
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/10">
          <p className="text-xs text-gray-500 text-center">
            Camera will auto-capture when fridge door opens. Images debounced to every 15 minutes.
          </p>
        </div>
      </div>
    </div>
  )
}

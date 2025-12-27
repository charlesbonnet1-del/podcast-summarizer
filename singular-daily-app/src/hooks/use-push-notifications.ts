"use client";

import { useState, useEffect, useCallback } from 'react';

// VAPID public key - generate yours at https://vapidkeys.com/
// Store private key securely on server (VAPID_PRIVATE_KEY env var)
const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY || '';

interface PushSubscriptionState {
  isSupported: boolean;
  isSubscribed: boolean;
  permission: NotificationPermission | 'default';
  loading: boolean;
  error: string | null;
}

export function usePushNotifications() {
  const [state, setState] = useState<PushSubscriptionState>({
    isSupported: false,
    isSubscribed: false,
    permission: 'default',
    loading: true,
    error: null,
  });

  // Check if push is supported
  useEffect(() => {
    const checkSupport = async () => {
      const isSupported = 
        'serviceWorker' in navigator && 
        'PushManager' in window &&
        'Notification' in window;

      if (!isSupported) {
        setState(prev => ({ 
          ...prev, 
          isSupported: false, 
          loading: false,
          error: 'Push notifications not supported in this browser'
        }));
        return;
      }

      // Get current permission
      const permission = Notification.permission;

      // Check if already subscribed
      let isSubscribed = false;
      try {
        const registration = await navigator.serviceWorker.ready;
        const subscription = await registration.pushManager.getSubscription();
        isSubscribed = subscription !== null;
      } catch (e) {
        console.error('[Push] Error checking subscription:', e);
      }

      setState(prev => ({
        ...prev,
        isSupported: true,
        isSubscribed,
        permission,
        loading: false,
      }));
    };

    checkSupport();
  }, []);

  // Register service worker
  const registerServiceWorker = useCallback(async () => {
    if (!('serviceWorker' in navigator)) {
      throw new Error('Service Worker not supported');
    }

    try {
      const registration = await navigator.serviceWorker.register('/sw.js', {
        scope: '/',
      });
      
      console.log('[Push] Service Worker registered:', registration.scope);
      
      // Wait for the service worker to be ready
      await navigator.serviceWorker.ready;
      
      return registration;
    } catch (error) {
      console.error('[Push] Service Worker registration failed:', error);
      throw error;
    }
  }, []);

  // Subscribe to push notifications
  const subscribe = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));

    try {
      // 1. Register service worker
      const registration = await registerServiceWorker();

      // 2. Request notification permission
      const permission = await Notification.requestPermission();
      
      if (permission !== 'granted') {
        setState(prev => ({ 
          ...prev, 
          permission,
          loading: false,
          error: 'Notification permission denied'
        }));
        return null;
      }

      // 3. Subscribe to push manager
      if (!VAPID_PUBLIC_KEY) {
        throw new Error('VAPID public key not configured');
      }

      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
      });

      console.log('[Push] Subscribed:', subscription);

      // 4. Send subscription to server
      const response = await fetch('/api/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(subscription.toJSON()),
      });

      if (!response.ok) {
        throw new Error('Failed to save subscription on server');
      }

      setState(prev => ({
        ...prev,
        isSubscribed: true,
        permission: 'granted',
        loading: false,
      }));

      return subscription;

    } catch (error) {
      console.error('[Push] Subscribe error:', error);
      setState(prev => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : 'Subscription failed',
      }));
      return null;
    }
  }, [registerServiceWorker]);

  // Unsubscribe from push notifications
  const unsubscribe = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));

    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.getSubscription();

      if (subscription) {
        // Unsubscribe locally
        await subscription.unsubscribe();

        // Remove from server
        await fetch('/api/push/subscribe', {
          method: 'DELETE',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ endpoint: subscription.endpoint }),
        });
      }

      setState(prev => ({
        ...prev,
        isSubscribed: false,
        loading: false,
      }));

      return true;

    } catch (error) {
      console.error('[Push] Unsubscribe error:', error);
      setState(prev => ({
        ...prev,
        loading: false,
        error: error instanceof Error ? error.message : 'Unsubscribe failed',
      }));
      return false;
    }
  }, []);

  // Send test notification (for debugging)
  const sendTestNotification = useCallback(async () => {
    try {
      const response = await fetch('/api/push/test', {
        method: 'POST',
      });
      return response.ok;
    } catch (error) {
      console.error('[Push] Test notification error:', error);
      return false;
    }
  }, []);

  return {
    ...state,
    subscribe,
    unsubscribe,
    sendTestNotification,
  };
}

// Helper: Convert VAPID key from base64 to Uint8Array
function urlBase64ToUint8Array(base64String: string): ArrayBuffer {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding)
    .replace(/-/g, '+')
    .replace(/_/g, '/');

  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);

  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }

  return outputArray.buffer;
}

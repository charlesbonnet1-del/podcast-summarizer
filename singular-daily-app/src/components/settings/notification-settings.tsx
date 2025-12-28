"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Bell, BellOff, Loader2, CheckCircle, AlertCircle, Info } from "lucide-react";
import { usePushNotifications } from "@/hooks/use-push-notifications";
import { toast } from "sonner";

export default function NotificationSettings() {
  const {
    isSupported,
    isSubscribed,
    permission,
    loading,
    error,
    subscribe,
    unsubscribe,
    sendTestNotification,
  } = usePushNotifications();

  const [testLoading, setTestLoading] = useState(false);

  const handleToggle = async () => {
    if (isSubscribed) {
      const success = await unsubscribe();
      if (success) {
        toast.success("Notifications désactivées");
      }
    } else {
      const subscription = await subscribe();
      if (subscription) {
        toast.success("Notifications activées !");
      }
    }
  };

  const handleTest = async () => {
    setTestLoading(true);
    const success = await sendTestNotification();
    setTestLoading(false);
    
    if (success) {
      toast.success("Notification envoyée !");
    } else {
      toast.error("Échec de l'envoi");
    }
  };

  // Not supported - show helpful message
  if (!isSupported) {
    return (
      <div className="p-4 rounded-xl bg-card border border-border/50">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-full bg-amber-500/10 flex items-center justify-center shrink-0">
            <Info className="w-5 h-5 text-amber-500" />
          </div>
          <div>
            <p className="font-display font-medium">Notifications Push</p>
            <p className="text-sm text-muted-foreground mt-1">
              Les notifications push nécessitent un navigateur récent (Chrome, Firefox, Safari 16+) et une connexion HTTPS.
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              💡 Essayez d'ouvrir Keernel dans Chrome ou Firefox pour activer cette fonctionnalité.
            </p>
          </div>
        </div>
      </div>
    );
  }

  // Permission denied
  if (permission === 'denied') {
    return (
      <div className="p-4 rounded-xl bg-card border border-border/50">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center shrink-0">
            <AlertCircle className="w-5 h-5 text-red-500" />
          </div>
          <div>
            <p className="font-display font-medium">Notifications bloquées</p>
            <p className="text-sm text-muted-foreground mt-1">
              Vous avez bloqué les notifications pour ce site.
            </p>
            <p className="text-xs text-muted-foreground mt-2">
              💡 Pour les réactiver, cliquez sur l'icône 🔒 dans la barre d'adresse, puis autorisez les notifications.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-xl bg-card border border-border/50">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
            isSubscribed 
              ? "bg-[#C5B358]/10" 
              : "bg-muted"
          }`}>
            {isSubscribed ? (
              <Bell className="w-5 h-5 text-[#C5B358]" />
            ) : (
              <BellOff className="w-5 h-5 text-muted-foreground" />
            )}
          </div>
          <div>
            <p className="font-display font-medium">Notifications Push</p>
            <p className="text-sm text-muted-foreground">
              {isSubscribed 
                ? "Recevez une alerte quand votre podcast est prêt" 
                : "Activez pour être notifié"
              }
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Test button (only when subscribed) */}
          {isSubscribed && (
            <motion.button
              onClick={handleTest}
              disabled={testLoading}
              className="px-3 py-1.5 text-xs rounded-lg bg-secondary hover:bg-secondary/80 transition-colors"
              whileTap={{ scale: 0.95 }}
            >
              {testLoading ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                "Tester"
              )}
            </motion.button>
          )}

          {/* Toggle button */}
          <motion.button
            onClick={handleToggle}
            disabled={loading}
            className={`relative w-14 h-8 rounded-full transition-colors ${
              isSubscribed 
                ? "bg-[#C5B358]" 
                : "bg-muted"
            }`}
            whileTap={{ scale: 0.95 }}
          >
            {loading ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <Loader2 className="w-4 h-4 animate-spin text-white" />
              </div>
            ) : (
              <motion.div
                className="absolute top-1 w-6 h-6 rounded-full bg-white shadow-md"
                animate={{ left: isSubscribed ? 30 : 4 }}
                transition={{ type: "spring", stiffness: 500, damping: 30 }}
              />
            )}
          </motion.button>
        </div>
      </div>

      {/* Status indicator */}
      {isSubscribed && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: "auto" }}
          className="mt-3 pt-3 border-t border-border/50"
        >
          <div className="flex items-center gap-2 text-sm text-emerald-600 dark:text-emerald-400">
            <CheckCircle className="w-4 h-4" />
            <span>Notifications actives sur cet appareil</span>
          </div>
        </motion.div>
      )}

      {/* Error display */}
      {error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="mt-3 pt-3 border-t border-border/50"
        >
          <p className="text-sm text-red-500">{error}</p>
        </motion.div>
      )}
    </div>
  );
}

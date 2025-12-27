import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";
import webpush from "web-push";

// Configure web-push with VAPID keys
const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY || '';
const VAPID_PRIVATE_KEY = process.env.VAPID_PRIVATE_KEY || '';
const VAPID_SUBJECT = process.env.VAPID_SUBJECT || 'mailto:contact@keernel.app';

if (VAPID_PUBLIC_KEY && VAPID_PRIVATE_KEY) {
  webpush.setVapidDetails(VAPID_SUBJECT, VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY);
}

// POST - Send test notification to current user
export async function POST() {
  const supabase = await createClient();
  
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    // Get user's subscriptions
    const { data: subscriptions, error } = await supabase
      .from("push_subscriptions")
      .select("endpoint, p256dh, auth")
      .eq("user_id", user.id);

    if (error) throw error;

    if (!subscriptions || subscriptions.length === 0) {
      return NextResponse.json(
        { error: "No push subscriptions found" }, 
        { status: 404 }
      );
    }

    // Prepare notification payload
    const payload = JSON.stringify({
      title: "🎙️ Test Keernel",
      body: "Les notifications fonctionnent !",
      icon: "/logo-charcoal.svg",
      url: "/dashboard"
    });

    // Send to all subscriptions
    const results = await Promise.allSettled(
      subscriptions.map(async (sub) => {
        const pushSubscription = {
          endpoint: sub.endpoint,
          keys: {
            p256dh: sub.p256dh,
            auth: sub.auth
          }
        };

        return webpush.sendNotification(pushSubscription, payload);
      })
    );

    // Count successes and failures
    const succeeded = results.filter(r => r.status === 'fulfilled').length;
    const failed = results.filter(r => r.status === 'rejected').length;

    // Clean up invalid subscriptions (410 Gone)
    for (let i = 0; i < results.length; i++) {
      const result = results[i];
      if (result.status === 'rejected') {
        const error = result.reason;
        if (error.statusCode === 410 || error.statusCode === 404) {
          // Subscription expired or invalid, remove it
          await supabase
            .from("push_subscriptions")
            .delete()
            .eq("endpoint", subscriptions[i].endpoint);
        }
      }
    }

    return NextResponse.json({ 
      success: true,
      sent: succeeded,
      failed: failed
    });

  } catch (error) {
    console.error("Error sending test notification:", error);
    return NextResponse.json(
      { error: "Failed to send notification" }, 
      { status: 500 }
    );
  }
}

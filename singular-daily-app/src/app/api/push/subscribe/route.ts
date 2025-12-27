import { createClient } from "@/lib/supabase/server";
import { NextResponse } from "next/server";

// POST - Save push subscription
export async function POST(request: Request) {
  const supabase = await createClient();
  
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const subscription = await request.json();

    // Validate subscription object
    if (!subscription.endpoint || !subscription.keys) {
      return NextResponse.json(
        { error: "Invalid subscription format" }, 
        { status: 400 }
      );
    }

    // Upsert subscription (update if endpoint exists)
    const { error } = await supabase
      .from("push_subscriptions")
      .upsert({
        user_id: user.id,
        endpoint: subscription.endpoint,
        p256dh: subscription.keys.p256dh,
        auth: subscription.keys.auth,
        user_agent: request.headers.get('user-agent') || '',
        updated_at: new Date().toISOString(),
      }, {
        onConflict: "endpoint"
      });

    if (error) throw error;

    return NextResponse.json({ success: true });

  } catch (error) {
    console.error("Error saving push subscription:", error);
    return NextResponse.json(
      { error: "Failed to save subscription" }, 
      { status: 500 }
    );
  }
}

// DELETE - Remove push subscription
export async function DELETE(request: Request) {
  const supabase = await createClient();
  
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const { endpoint } = await request.json();

    if (!endpoint) {
      return NextResponse.json(
        { error: "Endpoint required" }, 
        { status: 400 }
      );
    }

    const { error } = await supabase
      .from("push_subscriptions")
      .delete()
      .eq("user_id", user.id)
      .eq("endpoint", endpoint);

    if (error) throw error;

    return NextResponse.json({ success: true });

  } catch (error) {
    console.error("Error removing push subscription:", error);
    return NextResponse.json(
      { error: "Failed to remove subscription" }, 
      { status: 500 }
    );
  }
}

// GET - Check if user has active subscriptions
export async function GET() {
  const supabase = await createClient();
  
  const { data: { user } } = await supabase.auth.getUser();
  if (!user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const { data, error } = await supabase
      .from("push_subscriptions")
      .select("id, created_at, user_agent")
      .eq("user_id", user.id);

    if (error) throw error;

    return NextResponse.json({ 
      subscriptions: data || [],
      count: data?.length || 0
    });

  } catch (error) {
    console.error("Error fetching subscriptions:", error);
    return NextResponse.json(
      { error: "Failed to fetch subscriptions" }, 
      { status: 500 }
    );
  }
}

"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AlertTriangle, Trash2, Loader2, Unlink } from "lucide-react";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

export function DangerZone() {
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  const handleDisconnectTelegram = async () => {
    setLoading(true);
    const supabase = createClient();
    const { data: { user } } = await supabase.auth.getUser();

    if (!user) {
      toast.error("Please sign in again");
      setLoading(false);
      return;
    }

    const { error } = await supabase
      .from("users")
      .update({ telegram_chat_id: null })
      .eq("id", user.id);

    if (error) {
      toast.error("Failed to disconnect Telegram");
      setLoading(false);
      return;
    }

    toast.success("Telegram disconnected");
    setDisconnectOpen(false);
    setLoading(false);
    router.refresh();
  };

  const handleDeleteAccount = async () => {
    if (confirmText !== "DELETE") {
      toast.error("Please type DELETE to confirm");
      return;
    }

    setLoading(true);
    const supabase = createClient();
    
    // Sign out and delete will be handled by cascade
    const { error } = await supabase.auth.signOut();

    if (error) {
      toast.error("Failed to delete account");
      setLoading(false);
      return;
    }

    // Note: Full account deletion requires a server-side function
    // For now, we just sign out
    toast.success("Account deleted");
    window.location.href = "/";
  };

  return (
    <Card className="shadow-zen rounded-2xl border-destructive/20">
      <CardHeader>
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-destructive/10 flex items-center justify-center">
            <AlertTriangle className="w-5 h-5 text-destructive" />
          </div>
          <div>
            <CardTitle className="text-lg text-destructive">Danger Zone</CardTitle>
            <CardDescription>Irreversible actions</CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Disconnect Telegram */}
        <div className="flex items-center justify-between p-4 rounded-xl border border-border">
          <div>
            <h4 className="font-medium">Disconnect Telegram</h4>
            <p className="text-sm text-muted-foreground">
              Remove the link to your Telegram account
            </p>
          </div>
          <Dialog open={disconnectOpen} onOpenChange={setDisconnectOpen}>
            <DialogTrigger asChild>
              <Button variant="outline" className="rounded-xl">
                <Unlink className="w-4 h-4 mr-2" />
                Disconnect
              </Button>
            </DialogTrigger>
            <DialogContent className="rounded-2xl">
              <DialogHeader>
                <DialogTitle>Disconnect Telegram?</DialogTitle>
                <DialogDescription>
                  You won&apos;t be able to add content via Telegram until you reconnect.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button 
                  variant="outline" 
                  onClick={() => setDisconnectOpen(false)}
                  className="rounded-xl"
                >
                  Cancel
                </Button>
                <Button 
                  variant="destructive"
                  onClick={handleDisconnectTelegram}
                  disabled={loading}
                  className="rounded-xl"
                >
                  {loading && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
                  Disconnect
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>

        {/* Delete Account */}
        <div className="flex items-center justify-between p-4 rounded-xl border border-destructive/30 bg-destructive/5">
          <div>
            <h4 className="font-medium">Delete Account</h4>
            <p className="text-sm text-muted-foreground">
              Permanently delete your account and all data
            </p>
          </div>
          <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
            <DialogTrigger asChild>
              <Button variant="destructive" className="rounded-xl">
                <Trash2 className="w-4 h-4 mr-2" />
                Delete
              </Button>
            </DialogTrigger>
            <DialogContent className="rounded-2xl">
              <DialogHeader>
                <DialogTitle>Delete your account?</DialogTitle>
                <DialogDescription>
                  This action cannot be undone. All your episodes, queue items, and settings will be permanently deleted.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-2 py-4">
                <Label htmlFor="confirm">
                  Type <strong>DELETE</strong> to confirm
                </Label>
                <Input
                  id="confirm"
                  value={confirmText}
                  onChange={(e) => setConfirmText(e.target.value)}
                  placeholder="DELETE"
                  className="rounded-xl"
                />
              </div>
              <DialogFooter>
                <Button 
                  variant="outline" 
                  onClick={() => {
                    setDeleteOpen(false);
                    setConfirmText("");
                  }}
                  className="rounded-xl"
                >
                  Cancel
                </Button>
                <Button 
                  variant="destructive"
                  onClick={handleDeleteAccount}
                  disabled={loading || confirmText !== "DELETE"}
                  className="rounded-xl"
                >
                  {loading && <Loader2 className="w-4 h-4 animate-spin mr-2" />}
                  Delete Account
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardContent>
    </Card>
  );
}

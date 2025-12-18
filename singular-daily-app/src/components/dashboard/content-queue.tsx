"use client";

import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { 
  Youtube, 
  FileText, 
  Mic, 
  Trash2, 
  ExternalLink,
  Inbox
} from "lucide-react";
import type { ContentQueue as ContentQueueType } from "@/lib/types/database";
import { createClient } from "@/lib/supabase/client";
import { toast } from "sonner";
import { useRouter } from "next/navigation";

interface ContentQueueProps {
  items: ContentQueueType[];
}

export function ContentQueue({ items }: ContentQueueProps) {
  const router = useRouter();

  if (items.length === 0) {
    return (
      <Card className="shadow-zen rounded-2xl border-border">
        <CardContent className="py-12 text-center">
          <div className="w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center mx-auto mb-4">
            <Inbox className="w-8 h-8 text-muted-foreground" />
          </div>
          <h3 className="font-medium mb-1">Queue is empty</h3>
          <p className="text-sm text-muted-foreground max-w-sm mx-auto">
            Send YouTube links, articles, or podcast URLs to the Telegram bot to add them here.
          </p>
        </CardContent>
      </Card>
    );
  }

  const handleDelete = async (id: string) => {
    const supabase = createClient();
    const { error } = await supabase
      .from("content_queue")
      .delete()
      .eq("id", id);

    if (error) {
      toast.error("Failed to remove item");
      return;
    }

    toast.success("Item removed from queue");
    router.refresh();
  };

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <ContentItem 
          key={item.id} 
          item={item} 
          onDelete={() => handleDelete(item.id)}
        />
      ))}
    </div>
  );
}

function ContentItem({ 
  item, 
  onDelete 
}: { 
  item: ContentQueueType;
  onDelete: () => void;
}) {
  const getIcon = (sourceType: string) => {
    switch (sourceType) {
      case "youtube":
        return <Youtube className="w-4 h-4 text-red-500" />;
      case "podcast":
        return <Mic className="w-4 h-4 text-purple-500" />;
      default:
        return <FileText className="w-4 h-4 text-blue-500" />;
    }
  };

  const getSourceColor = (sourceType: string) => {
    switch (sourceType) {
      case "youtube":
        return "bg-red-500/10 text-red-600";
      case "podcast":
        return "bg-purple-500/10 text-purple-600";
      default:
        return "bg-blue-500/10 text-blue-600";
    }
  };

  const formatUrl = (url: string) => {
    try {
      const parsed = new URL(url);
      return parsed.hostname.replace("www.", "");
    } catch {
      return url.slice(0, 30);
    }
  };

  const timeAgo = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${diffDays}d ago`;
  };

  return (
    <Card className="shadow-zen rounded-xl border-border hover:border-border/80 transition-colors">
      <CardContent className="p-3">
        <div className="flex items-center gap-3">
          {/* Icon */}
          <div className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${getSourceColor(item.source_type)}`}>
            {getIcon(item.source_type)}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <p className="font-medium truncate text-sm">
              {item.title || formatUrl(item.url)}
            </p>
            <div className="flex items-center gap-2 mt-0.5">
              <Badge variant="secondary" className="rounded text-xs capitalize">
                {item.source_type}
              </Badge>
              <span className="text-xs text-muted-foreground">
                {timeAgo(item.created_at)}
              </span>
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1 shrink-0">
            <a href={item.url} target="_blank" rel="noopener noreferrer">
              <Button variant="ghost" size="icon" className="rounded-lg h-8 w-8">
                <ExternalLink className="w-3.5 h-3.5" />
              </Button>
            </a>
            <Button 
              variant="ghost" 
              size="icon" 
              className="rounded-lg h-8 w-8 text-muted-foreground hover:text-destructive"
              onClick={onDelete}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

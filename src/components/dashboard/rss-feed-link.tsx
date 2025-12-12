"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Copy, Check, ExternalLink } from "lucide-react";
import { toast } from "sonner";

interface RssFeedLinkProps {
  feedUrl: string;
}

export function RssFeedLink({ feedUrl }: RssFeedLinkProps) {
  const [copied, setCopied] = useState(false);

  const copyUrl = async () => {
    await navigator.clipboard.writeText(feedUrl);
    setCopied(true);
    toast.success("RSS feed URL copied!");
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <div className="flex-1 bg-secondary rounded-xl px-4 py-3 text-sm truncate font-mono">
          {feedUrl}
        </div>
        <Button
          variant="outline"
          size="icon"
          className="rounded-xl h-12 w-12 shrink-0"
          onClick={copyUrl}
        >
          {copied ? (
            <Check className="w-4 h-4 text-green-500" />
          ) : (
            <Copy className="w-4 h-4" />
          )}
        </Button>
      </div>

      <div className="flex flex-wrap gap-2">
        <SubscribeButton 
          label="Apple Podcasts"
          url={`podcast://${feedUrl.replace(/^https?:\/\//, "")}`}
          color="bg-purple-500/10 text-purple-600 hover:bg-purple-500/20"
        />
        <SubscribeButton 
          label="Overcast"
          url={`overcast://x-callback-url/add?url=${encodeURIComponent(feedUrl)}`}
          color="bg-orange-500/10 text-orange-600 hover:bg-orange-500/20"
        />
        <SubscribeButton 
          label="Pocket Casts"
          url={`pktc://subscribe/${feedUrl}`}
          color="bg-red-500/10 text-red-600 hover:bg-red-500/20"
        />
      </div>
    </div>
  );
}

function SubscribeButton({ 
  label, 
  url, 
  color 
}: { 
  label: string; 
  url: string; 
  color: string;
}) {
  return (
    <a href={url} target="_blank" rel="noopener noreferrer">
      <Button 
        variant="ghost" 
        size="sm" 
        className={`rounded-lg text-xs ${color}`}
      >
        {label}
        <ExternalLink className="w-3 h-3 ml-1" />
      </Button>
    </a>
  );
}

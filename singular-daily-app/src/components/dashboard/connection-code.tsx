"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Copy, Check, ExternalLink } from "lucide-react";
import { toast } from "sonner";

interface ConnectionCodeProps {
  code: string;
  telegramConnected: boolean;
}

export function ConnectionCode({ code, telegramConnected }: ConnectionCodeProps) {
  const [copied, setCopied] = useState(false);

  const copyCode = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    toast.success("Code copied to clipboard!");
    setTimeout(() => setCopied(false), 2000);
  };

  if (telegramConnected) {
    return (
      <div className="flex items-center gap-2">
        <Badge variant="secondary" className="bg-green-500/10 text-green-600 rounded-lg px-3 py-1">
          <Check className="w-3 h-3 mr-1" />
          Connected
        </Badge>
        <span className="text-sm text-muted-foreground">
          Your Telegram is linked
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <div className="flex-1 bg-secondary rounded-xl px-4 py-3 font-mono text-2xl tracking-[0.3em] text-center">
          {code}
        </div>
        <Button
          variant="outline"
          size="icon"
          className="rounded-xl h-12 w-12"
          onClick={copyCode}
        >
          {copied ? (
            <Check className="w-4 h-4 text-green-500" />
          ) : (
            <Copy className="w-4 h-4" />
          )}
        </Button>
      </div>
      
      <div className="text-sm text-muted-foreground space-y-2">
        <p>To connect:</p>
        <ol className="list-decimal list-inside space-y-1 ml-1">
          <li>Open <a 
            href="https://t.me/Mets_tes_bot" 
            target="_blank" 
            rel="noopener noreferrer"
            className="text-[#0088cc] hover:underline inline-flex items-center gap-1"
          >
            @Mets_tes_bot
            <ExternalLink className="w-3 h-3" />
          </a></li>
          <li>Send the command <code className="bg-secondary px-1.5 py-0.5 rounded">/start</code></li>
          <li>Enter your connection code: <strong>{code}</strong></li>
        </ol>
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { motion } from "framer-motion";
import { createClient } from "@/lib/supabase/client";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LayoutDashboard, Settings, LogOut, User as UserIcon } from "lucide-react";
import { ThemeToggle } from "@/components/theme-toggle";
import type { User } from "@supabase/supabase-js";
import type { User as UserProfile } from "@/lib/types/database";

interface DashboardNavProps {
  user: User;
  profile: UserProfile | null;
}

export function DashboardNav({ user, profile }: DashboardNavProps) {
  const pathname = usePathname();
  const supabase = createClient();
  const { resolvedTheme } = useTheme();

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    window.location.href = "/";
  };

  const navItems = [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
    { href: "/settings", label: "Settings", icon: Settings },
  ];

  const displayName = profile?.first_name || user.email?.split("@")[0] || "User";
  const initials = profile?.first_name 
    ? profile.first_name.slice(0, 2).toUpperCase()
    : user.email?.slice(0, 2).toUpperCase() ?? "U";

  // Logo based on theme - default to charcoal for SSR
  const logoSrc = resolvedTheme === "dark" ? "/logo-sable.svg" : "/logo-charcoal.svg";

  return (
    <header className="fixed top-0 left-0 right-0 z-50">
      <div className="glass-card mx-4 mt-4 px-6 h-14 flex items-center justify-between">
        {/* Logo + Greeting */}
        <div className="flex items-center gap-4">
          <Link href="/dashboard" className="flex items-center gap-3">
            {/* Keernel Logo - SVG based on theme */}
            <Image 
              src={logoSrc}
              alt="Keernel"
              width={32}
              height={32}
              className="w-8 h-8"
            />
            <span className="title-keernel text-xl text-foreground">
              Keernel
            </span>
          </Link>
          <span className="text-muted-foreground text-sm hidden md:inline font-body">
            Hello, <span className="text-foreground font-medium">{displayName}</span>
          </span>
        </div>

        {/* Navigation */}
        <nav className="hidden md:flex items-center gap-1">
          {navItems.map((item) => {
            const isActive = pathname === item.href;
            const Icon = item.icon;
            return (
              <Link key={item.href} href={item.href}>
                <motion.div
                  className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium font-mono transition-colors ${
                    isActive 
                      ? "bg-card text-foreground" 
                      : "text-muted-foreground hover:text-foreground hover:bg-card/50"
                  }`}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </motion.div>
              </Link>
            );
          })}
        </nav>

        {/* Right side */}
        <div className="flex items-center gap-2">
          <ThemeToggle />
          
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <motion.button 
                className="flex items-center gap-2 px-3 py-1.5 rounded-xl hover:bg-card/50 transition-colors"
                whileHover={{ scale: 1.02 }}
                whileTap={{ scale: 0.98 }}
              >
                <Avatar className="w-8 h-8">
                  <AvatarFallback className="bg-brass text-charcoal text-sm font-medium font-mono">
                    {initials}
                  </AvatarFallback>
                </Avatar>
                <span className="hidden sm:inline text-sm font-medium font-mono">
                  {displayName}
                </span>
              </motion.button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56 glass-card border-none">
              <div className="px-3 py-2">
                <p className="text-sm font-medium font-body">
                  {profile?.first_name && profile?.last_name 
                    ? `${profile.first_name} ${profile.last_name}`
                    : user.email
                  }
                </p>
                <p className="text-xs text-muted-foreground capitalize font-mono">
                  {profile?.subscription_status ?? "free"} plan
                </p>
              </div>
              <DropdownMenuSeparator className="bg-border/50" />
              <DropdownMenuItem asChild className="rounded-lg cursor-pointer font-mono">
                <Link href="/settings" className="flex items-center gap-2">
                  <UserIcon className="w-4 h-4" />
                  Account Settings
                </Link>
              </DropdownMenuItem>
              <DropdownMenuSeparator className="bg-border/50" />
              <DropdownMenuItem
                onClick={handleSignOut}
                className="rounded-lg cursor-pointer text-destructive focus:text-destructive font-mono"
              >
                <LogOut className="w-4 h-4 mr-2" />
                Sign Out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  );
}

"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { 
  Newspaper, 
  Archive, 
  Headphones, 
  Settings,
  Menu,
  X,
  LogOut,
  User,
  Sun,
  Moon
} from "lucide-react";
import { useTheme } from "next-themes";
import { cn } from "@/lib/utils";
import { createClient } from "@/lib/supabase/client";
import { useRouter } from "next/navigation";

// ============================================
// TYPES
// ============================================

interface DashboardNavProps {
  user: {
    firstName: string;
    email: string;
    avatarUrl?: string;
  };
}

// ============================================
// NAV ITEMS
// ============================================

const NAV_ITEMS = [
  { 
    href: "/dashboard", 
    label: "Feed", 
    icon: Newspaper,
    description: "Briefings du jour"
  },
  { 
    href: "/dashboard/archive", 
    label: "Archive", 
    icon: Archive,
    description: "Historique"
  },
  { 
    href: "/dashboard/podcast", 
    label: "Podcast", 
    icon: Headphones,
    description: "Écouter"
  },
  { 
    href: "/dashboard/settings", 
    label: "Paramètres", 
    icon: Settings,
    description: "Configurer"
  },
];

// ============================================
// DASHBOARD NAV COMPONENT
// ============================================

export function DashboardNav({ user }: DashboardNavProps) {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  
  const supabase = createClient();

  const handleSignOut = async () => {
    await supabase.auth.signOut();
    router.push("/login");
  };

  const isActive = (href: string) => {
    if (href === "/dashboard") {
      return pathname === "/dashboard" || pathname === "/dashboard/feed";
    }
    return pathname.startsWith(href);
  };

  return (
    <>
      {/* Desktop Nav - Sidebar */}
      <nav className="hidden md:flex fixed left-0 top-0 bottom-0 w-64 flex-col bg-card border-r border-border z-40">
        {/* Logo */}
        <div className="p-6 border-b border-border">
          <Link href="/dashboard" className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center">
              <span className="text-lg font-bold text-primary-foreground">K</span>
            </div>
            <div>
              <h1 className="font-semibold text-foreground">Keernel</h1>
              <p className="text-xs text-muted-foreground">Intelligence Platform</p>
            </div>
          </Link>
        </div>

        {/* Nav Items */}
        <div className="flex-1 p-4 space-y-1">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 px-4 py-3 rounded-xl transition-all group",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted"
                )}
              >
                <Icon className={cn("w-5 h-5", active ? "" : "group-hover:text-primary")} />
                <div>
                  <span className="font-medium">{item.label}</span>
                  <p className={cn(
                    "text-xs",
                    active ? "text-primary-foreground/70" : "text-muted-foreground"
                  )}>
                    {item.description}
                  </p>
                </div>
              </Link>
            );
          })}
        </div>

        {/* User section */}
        <div className="p-4 border-t border-border">
          {/* Theme toggle */}
          <button
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            className="w-full flex items-center gap-3 px-4 py-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted transition-all mb-2"
          >
            {theme === "dark" ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
            <span className="text-sm">{theme === "dark" ? "Mode clair" : "Mode sombre"}</span>
          </button>
          
          {/* User info */}
          <div className="flex items-center gap-3 px-4 py-3">
            <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
              {user.avatarUrl ? (
                <img src={user.avatarUrl} alt="" className="w-full h-full rounded-full object-cover" />
              ) : (
                <User className="w-5 h-5 text-muted-foreground" />
              )}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">
                {user.firstName || "Utilisateur"}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {user.email}
              </p>
            </div>
          </div>
          
          {/* Sign out */}
          <button
            onClick={handleSignOut}
            className="w-full flex items-center gap-3 px-4 py-2 rounded-xl text-muted-foreground hover:text-red-500 hover:bg-red-500/10 transition-all"
          >
            <LogOut className="w-5 h-5" />
            <span className="text-sm">Déconnexion</span>
          </button>
        </div>
      </nav>

      {/* Mobile Nav - Top bar */}
      <nav className="md:hidden fixed top-0 left-0 right-0 h-16 bg-card/80 backdrop-blur-xl border-b border-border z-40">
        <div className="flex items-center justify-between h-full px-4">
          <Link href="/dashboard" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center">
              <span className="text-sm font-bold text-primary-foreground">K</span>
            </div>
            <span className="font-semibold text-foreground">Keernel</span>
          </Link>
          
          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="p-2 rounded-lg hover:bg-muted"
          >
            {isMobileMenuOpen ? (
              <X className="w-6 h-6" />
            ) : (
              <Menu className="w-6 h-6" />
            )}
          </button>
        </div>

        {/* Mobile menu */}
        {isMobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className="absolute top-16 left-0 right-0 bg-card border-b border-border p-4 space-y-2"
          >
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active = isActive(item.href);
              
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setIsMobileMenuOpen(false)}
                  className={cn(
                    "flex items-center gap-3 px-4 py-3 rounded-xl transition-all",
                    active
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted"
                  )}
                >
                  <Icon className="w-5 h-5" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
            
            <div className="border-t border-border pt-2 mt-2">
              <button
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-muted-foreground hover:bg-muted"
              >
                {theme === "dark" ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
                <span>{theme === "dark" ? "Mode clair" : "Mode sombre"}</span>
              </button>
              
              <button
                onClick={handleSignOut}
                className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-red-500 hover:bg-red-500/10"
              >
                <LogOut className="w-5 h-5" />
                <span>Déconnexion</span>
              </button>
            </div>
          </motion.div>
        )}
      </nav>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 h-16 bg-card/80 backdrop-blur-xl border-t border-border z-40">
        <div className="flex items-center justify-around h-full">
          {NAV_ITEMS.slice(0, 4).map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);
            
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex flex-col items-center gap-1 p-2 rounded-xl transition-all",
                  active ? "text-primary" : "text-muted-foreground"
                )}
              >
                <Icon className="w-5 h-5" />
                <span className="text-xs">{item.label}</span>
              </Link>
            );
          })}
        </div>
      </nav>
    </>
  );
}

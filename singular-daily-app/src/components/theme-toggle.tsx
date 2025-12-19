"use client";

import * as React from "react";
import { motion } from "framer-motion";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="w-9 h-9 flex items-center justify-center">
        <Sun className="h-4 w-4 text-muted-foreground" />
      </div>
    );
  }

  return (
    <motion.button
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      className="w-9 h-9 flex items-center justify-center rounded-xl hover:bg-secondary/50 dark:hover:bg-white/5 transition-colors"
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
    >
      <motion.div
        initial={false}
        animate={{ rotate: theme === "dark" ? 180 : 0 }}
        transition={{ duration: 0.3, ease: "easeInOut" }}
      >
        {theme === "dark" ? (
          <Sun className="h-4 w-4 text-[#CCFF00]" />
        ) : (
          <Moon className="h-4 w-4 text-[#00F5FF]" />
        )}
      </motion.div>
      <span className="sr-only">Toggle theme</span>
    </motion.button>
  );
}

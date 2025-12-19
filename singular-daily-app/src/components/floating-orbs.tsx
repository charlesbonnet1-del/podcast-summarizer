"use client";

import { motion } from "framer-motion";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";

export function FloatingOrbs() {
  const { resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Don't render orbs in dark mode
  if (!mounted || resolvedTheme === "dark") {
    return null;
  }

  return (
    <div className="fixed inset-0 overflow-hidden pointer-events-none z-0">
      {/* Cyan Orb - Top Right */}
      <motion.div
        className="absolute -top-32 -right-32 w-[600px] h-[600px] rounded-full opacity-30"
        style={{
          background: "radial-gradient(circle, #00F5FF 0%, transparent 70%)",
          filter: "blur(60px)",
        }}
        animate={{
          x: [0, 50, -30, 0],
          y: [0, -40, 30, 0],
          scale: [1, 1.1, 0.95, 1],
        }}
        transition={{
          duration: 20,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      {/* Lime Orb - Bottom Left */}
      <motion.div
        className="absolute -bottom-48 -left-48 w-[500px] h-[500px] rounded-full opacity-25"
        style={{
          background: "radial-gradient(circle, #CCFF00 0%, transparent 70%)",
          filter: "blur(80px)",
        }}
        animate={{
          x: [0, -40, 60, 0],
          y: [0, 50, -30, 0],
          scale: [1, 0.9, 1.1, 1],
        }}
        transition={{
          duration: 25,
          repeat: Infinity,
          ease: "easeInOut",
          delay: 2,
        }}
      />

      {/* Small Cyan accent - Center Left */}
      <motion.div
        className="absolute top-1/3 -left-20 w-[300px] h-[300px] rounded-full opacity-20"
        style={{
          background: "radial-gradient(circle, #00F5FF 0%, transparent 70%)",
          filter: "blur(50px)",
        }}
        animate={{
          x: [0, 30, -20, 0],
          y: [0, -60, 40, 0],
        }}
        transition={{
          duration: 18,
          repeat: Infinity,
          ease: "easeInOut",
          delay: 5,
        }}
      />

      {/* Small Lime accent - Top Center */}
      <motion.div
        className="absolute -top-20 left-1/2 w-[250px] h-[250px] rounded-full opacity-15"
        style={{
          background: "radial-gradient(circle, #CCFF00 0%, transparent 70%)",
          filter: "blur(40px)",
        }}
        animate={{
          x: [0, -50, 30, 0],
          y: [0, 40, -20, 0],
        }}
        transition={{
          duration: 22,
          repeat: Infinity,
          ease: "easeInOut",
          delay: 8,
        }}
      />
    </div>
  );
}

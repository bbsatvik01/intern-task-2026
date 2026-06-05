"use client";

import { useEffect, useState } from "react";

export default function MilestoneToast({
  streak,
  show,
  onDone,
}: {
  streak: number;
  show: boolean;
  onDone: () => void;
}) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (show) {
      setVisible(true);
      const t = setTimeout(() => {
        setVisible(false);
        setTimeout(onDone, 300);
      }, 2500);
      return () => clearTimeout(t);
    }
  }, [show, onDone]);

  if (!show && !visible) return null;

  return (
    <div
      className={`fixed bottom-28 left-1/2 -translate-x-1/2 z-50 px-6 py-3 rounded-2xl bg-gradient-to-r from-orange-400 to-red-500 text-white font-bold shadow-lg flex items-center gap-3 text-sm transition-all duration-300 ${
        visible ? "opacity-100 translate-y-0 scale-100" : "opacity-0 translate-y-4 scale-95"
      }`}
    >
      <span className="text-2xl">🔥</span>
      <span>{streak} streak! Keep it up!</span>
      <span className="text-2xl">🎉</span>
    </div>
  );
}

"use client";

import { motion, AnimatePresence } from "motion/react";
import type { LunaState } from "@/lib/types";

const STATE_LABELS: Record<LunaState, string> = {
  idle: "Ready to chat",
  speaking: "Speaking...",
  listening: "Listening...",
  happy: "Great job!",
  thinking: "Thinking...",
};

const STATE_COLORS: Record<LunaState, string> = {
  idle: "text-slate-400",
  speaking: "text-brand",
  listening: "text-brand",
  happy: "text-green-500",
  thinking: "text-amber-500",
};

export default function Luna({ state }: { state: LunaState }) {
  return (
    <div className="flex flex-col items-center select-none">
      {/* Container with motion for state transitions */}
      <motion.div
        animate={{
          scale: state === "happy" ? [1, 1.08, 0.97, 1] : 1,
          y: state === "speaking" ? [0, -3, 0] : state === "idle" ? [0, -6, 0] : 0,
        }}
        transition={{
          y: { duration: state === "speaking" ? 0.6 : 3, repeat: Infinity, ease: "easeInOut" },
          scale: { duration: 0.5 },
        }}
      >
        <svg className="w-44 h-52" viewBox="0 0 200 240" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="body-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#A78BFA" />
              <stop offset="100%" stopColor="#8560E0" />
            </linearGradient>
            <linearGradient id="glow-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#A78BFA" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#8560E0" stopOpacity={0} />
            </linearGradient>
            <filter id="soft-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx={0} dy={4} stdDeviation={8} floodColor="#8560E0" floodOpacity={0.2} />
            </filter>
            <filter id="thinking-glow">
              <feGaussianBlur stdDeviation={6} result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {/* Glow ring — visible when speaking */}
          <AnimatePresence>
            {state === "speaking" && (
              <motion.circle
                cx={100} cy={110} r={85} fill="none" stroke="url(#glow-grad)" strokeWidth={3}
                initial={{ opacity: 0, r: 75 }}
                animate={{ opacity: [0.3, 0.7, 0.3], r: [80, 90, 80] }}
                exit={{ opacity: 0 }}
                transition={{ duration: 2, repeat: Infinity }}
              />
            )}
          </AnimatePresence>

          {/* Body */}
          <g filter="url(#soft-shadow)">
            <ellipse cx={100} cy={120} rx={65} ry={70} fill="url(#body-grad)" />
            <ellipse cx={100} cy={110} rx={40} ry={38} fill="white" opacity={0.15} />
          </g>

          {/* Eyes */}
          <motion.g
            animate={state === "idle" ? { scaleY: [1, 1, 0.1, 1, 1] } : { scaleY: 1 }}
            transition={state === "idle" ? { duration: 4, repeat: Infinity, times: [0, 0.92, 0.95, 0.98, 1] } : {}}
            style={{ transformOrigin: "100px 105px" }}
          >
            <ellipse cx={80} cy={105} rx={8} ry={9} fill="white" />
            <ellipse cx={120} cy={105} rx={8} ry={9} fill="white" />
            {/* Pupils — shift based on state */}
            <motion.circle
              cx={82} cy={106} r={5} fill="#1e293b"
              animate={{ cx: state === "listening" ? 78 : state === "speaking" ? 84 : 82 }}
              transition={{ duration: 0.3 }}
            />
            <motion.circle
              cx={122} cy={106} r={5} fill="#1e293b"
              animate={{ cx: state === "listening" ? 118 : state === "speaking" ? 124 : 122 }}
              transition={{ duration: 0.3 }}
            />
            {/* Eye shine */}
            <circle cx={84} cy={103} r={2} fill="white" opacity={0.9} />
            <circle cx={124} cy={103} r={2} fill="white" opacity={0.9} />
          </motion.g>

          {/* Brows */}
          <motion.path
            d="M70 94 Q80 89 90 94" fill="none" stroke="#7C3AED" strokeWidth={2} strokeLinecap="round"
            animate={{ d: state === "happy" ? "M70 90 Q80 84 90 90" : "M70 94 Q80 89 90 94" }}
            transition={{ duration: 0.3 }}
          />
          <motion.path
            d="M110 94 Q120 89 130 94" fill="none" stroke="#7C3AED" strokeWidth={2} strokeLinecap="round"
            animate={{ d: state === "happy" ? "M110 90 Q120 84 130 90" : "M110 94 Q120 89 130 94" }}
            transition={{ duration: 0.3 }}
          />

          {/* Mouth — idle smile */}
          <AnimatePresence mode="wait">
            {state === "idle" || state === "listening" ? (
              <motion.path
                key="idle-mouth"
                d="M88 128 Q100 138 112 128"
                fill="none" stroke="#7C3AED" strokeWidth={2.5} strokeLinecap="round"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              />
            ) : state === "speaking" ? (
              <motion.ellipse
                key="speak-mouth"
                cx={100} cy={132} fill="#7C3AED"
                initial={{ rx: 8, ry: 4, opacity: 0 }}
                animate={{ rx: [8, 11, 8], ry: [4, 8, 4], opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ rx: { duration: 0.4, repeat: Infinity }, ry: { duration: 0.4, repeat: Infinity } }}
              />
            ) : state === "happy" ? (
              <motion.path
                key="happy-mouth"
                d="M82 126 Q100 148 118 126"
                fill="#7C3AED"
                initial={{ opacity: 0, d: "M88 128 Q100 138 112 128" }}
                animate={{ opacity: 1, d: "M82 126 Q100 148 118 126" }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
              />
            ) : state === "thinking" ? (
              <g key="thinking-mouth">
                {/* Thinking: animated bouncing dots with glow */}
                {[0, 1, 2].map((i) => (
                  <motion.circle
                    key={i}
                    cx={88 + i * 12} cy={132} r={3.5} fill="#7C3AED"
                    filter="url(#thinking-glow)"
                    animate={{
                      y: [0, -6, 0],
                      opacity: [0.4, 1, 0.4],
                      r: [3, 4, 3],
                    }}
                    transition={{
                      duration: 0.8,
                      delay: i * 0.15,
                      repeat: Infinity,
                      ease: "easeInOut",
                    }}
                  />
                ))}
              </g>
            ) : null}
          </AnimatePresence>

          {/* Blush — stronger when happy */}
          <motion.circle
            cx={68} cy={118} r={10} fill="#f9a8d4"
            animate={{ opacity: state === "happy" ? 0.6 : 0.25 }}
            transition={{ duration: 0.3 }}
          />
          <motion.circle
            cx={132} cy={118} r={10} fill="#f9a8d4"
            animate={{ opacity: state === "happy" ? 0.6 : 0.25 }}
            transition={{ duration: 0.3 }}
          />

          {/* Sound waves — speaking */}
          <AnimatePresence>
            {state === "speaking" && (
              <motion.g
                initial={{ opacity: 0, x: -5 }}
                animate={{ opacity: [0.6, 1, 0.6], x: [0, 4, 0] }}
                exit={{ opacity: 0 }}
                transition={{ duration: 1, repeat: Infinity }}
              >
                <path d="M165 100 Q175 110 165 120" fill="none" stroke="#A78BFA" strokeWidth={2} strokeLinecap="round" opacity={0.7} />
                <path d="M172 93 Q185 110 172 127" fill="none" stroke="#A78BFA" strokeWidth={2} strokeLinecap="round" opacity={0.5} />
                <path d="M179 86 Q195 110 179 134" fill="none" stroke="#A78BFA" strokeWidth={2} strokeLinecap="round" opacity={0.3} />
              </motion.g>
            )}
          </AnimatePresence>

          {/* Listen indicator — green pulses */}
          <AnimatePresence>
            {state === "listening" && (
              <motion.g
                initial={{ opacity: 0 }}
                animate={{ opacity: [0.5, 1, 0.5] }}
                exit={{ opacity: 0 }}
                transition={{ duration: 1.2, repeat: Infinity }}
              >
                <circle cx={35} cy={110} r={8} fill="#22c55e" opacity={0.4} />
                <circle cx={35} cy={110} r={12} fill="#22c55e" opacity={0.2} />
                <circle cx={35} cy={110} r={16} fill="#22c55e" opacity={0.1} />
              </motion.g>
            )}
          </AnimatePresence>

          {/* Sparkles — happy */}
          <AnimatePresence>
            {state === "happy" && (
              <g>
                {[
                  { x: 40, y: 70, size: 16, delay: 0 },
                  { x: 150, y: 80, size: 12, delay: 0.1 },
                  { x: 55, y: 170, size: 14, delay: 0.2 },
                  { x: 148, y: 158, size: 10, delay: 0.15 },
                ].map((s, i) => (
                  <motion.text
                    key={i}
                    x={s.x} y={s.y} fontSize={s.size} fill="#fbbf24"
                    initial={{ opacity: 0, y: 10, scale: 0 }}
                    animate={{ opacity: [0, 1, 0], y: [10, -10, -25], scale: [0, 1.3, 0.5] }}
                    transition={{ duration: 1.3, delay: s.delay }}
                  >
                    ✦
                  </motion.text>
                ))}
              </g>
            )}
          </AnimatePresence>

          {/* Thinking orbit ring */}
          <AnimatePresence>
            {state === "thinking" && (
              <motion.ellipse
                cx={100} cy={110} rx={75} ry={30}
                fill="none" stroke="#A78BFA" strokeWidth={1.5}
                strokeDasharray="8 6"
                initial={{ opacity: 0, rotate: 0 }}
                animate={{ opacity: 0.3, rotate: 360 }}
                exit={{ opacity: 0 }}
                transition={{ rotate: { duration: 3, repeat: Infinity, ease: "linear" }, opacity: { duration: 0.3 } }}
                style={{ transformOrigin: "100px 110px" }}
              />
            )}
          </AnimatePresence>

          {/* Labels */}
          <text x={100} y={210} textAnchor="middle" fill="#8560E0" fontWeight={700} fontSize={14} opacity={0.8}>Luna</text>
          <text x={100} y={226} textAnchor="middle" fill="#94a3b8" fontWeight={500} fontSize={10}>Language Tutor</text>
        </svg>
      </motion.div>

      {/* State label with animation */}
      <motion.p
        className={`mt-1 text-xs font-semibold transition-colors ${STATE_COLORS[state]}`}
        key={state}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.2 }}
      >
        {STATE_LABELS[state]}
      </motion.p>
    </div>
  );
}

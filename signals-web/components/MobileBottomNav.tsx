'use client';

import React from 'react';

interface MobileBottomNavProps {
  activeTab: 'signals' | 'ea' | 'journal' | 'positions' | 'accounts';
  setActiveTab: (tab: 'signals' | 'ea' | 'journal' | 'positions' | 'accounts') => void;
  eaRunning: boolean;
  positionsCount: number;
}

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({
  activeTab,
  setActiveTab,
  eaRunning,
  positionsCount,
}) => {
  const tabs = [
    {
      id: 'signals' as const,
      label: 'Signals',
      icon: '📡',
      activeColor: 'text-amber-400',
      activeBorder: 'border-amber-400/40',
      activeBg: 'bg-amber-500/10',
    },
    {
      id: 'ea' as const,
      label: 'EA Bot',
      icon: '⚡',
      badge: eaRunning ? 'ON' : 'OFF',
      badgeColor: eaRunning ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400',
      activeColor: 'text-emerald-400',
      activeBorder: 'border-emerald-400/40',
      activeBg: 'bg-emerald-500/10',
    },
    {
      id: 'journal' as const,
      label: 'Journal',
      icon: '📖',
      activeColor: 'text-cyan-400',
      activeBorder: 'border-cyan-400/40',
      activeBg: 'bg-cyan-500/10',
    },
    {
      id: 'positions' as const,
      label: 'Positions',
      icon: '📊',
      badge: positionsCount > 0 ? String(positionsCount) : undefined,
      badgeColor: 'bg-purple-500/20 text-purple-300',
      activeColor: 'text-purple-400',
      activeBorder: 'border-purple-400/40',
      activeBg: 'bg-purple-500/10',
    },
    {
      id: 'accounts' as const,
      label: 'Accounts',
      icon: '🏦',
      activeColor: 'text-slate-200',
      activeBorder: 'border-slate-400/40',
      activeBg: 'bg-slate-700/20',
    },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-50 lg:hidden backdrop-blur-2xl bg-[#080b11]/95 border-t border-white/[0.08] px-2 py-1.5 pb-[max(0.5rem,env(safe-area-inset-bottom))] shadow-[0_-10px_25px_rgba(0,0,0,0.5)]">
      <div className="flex items-center justify-around gap-1 max-w-lg mx-auto">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative flex flex-col items-center justify-center flex-1 py-1 px-1 rounded-xl transition-all duration-200 min-h-[48px] ${
                isActive
                  ? `${tab.activeBg} ${tab.activeColor} border ${tab.activeBorder}`
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <div className="relative text-lg leading-none">
                <span>{tab.icon}</span>
                {tab.badge && (
                  <span
                    className={`absolute -top-1.5 -right-3 text-[8px] font-mono font-bold px-1 rounded-full ${tab.badgeColor} border border-white/10`}
                  >
                    {tab.badge}
                  </span>
                )}
              </div>
              <span className={`text-[10px] font-semibold mt-0.5 ${isActive ? 'font-bold' : ''}`}>
                {tab.label}
              </span>
              {isActive && (
                <div
                  className={`w-1 h-1 rounded-full mt-0.5 ${
                    tab.id === 'signals'
                      ? 'bg-amber-400 shadow-[0_0_6px_#f59e0b]'
                      : tab.id === 'ea'
                      ? 'bg-emerald-400 shadow-[0_0_6px_#10b981]'
                      : tab.id === 'journal'
                      ? 'bg-cyan-400 shadow-[0_0_6px_#06b6d4]'
                      : tab.id === 'positions'
                      ? 'bg-purple-400 shadow-[0_0_6px_#a855f7]'
                      : 'bg-slate-300'
                  }`}
                ></div>
              )}
            </button>
          );
        })}
      </div>
    </nav>
  );
};

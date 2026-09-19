'use client';

import React, { useState, useEffect } from 'react';

export const PWAInstallBanner: React.FC = () => {
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [isInstallable, setIsInstallable] = useState(false);
  const [isIOS, setIsIOS] = useState(false);
  const [isStandalone, setIsStandalone] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Check if already running in standalone PWA mode
    if (
      window.matchMedia('(display-mode: standalone)').matches ||
      (window.navigator as any).standalone === true
    ) {
      setIsStandalone(true);
      return;
    }

    // Check iOS
    const userAgent = window.navigator.userAgent.toLowerCase();
    const isIosDevice = /iphone|ipad|ipod/.test(userAgent);
    setIsIOS(isIosDevice);

    // Android/Desktop Chrome install prompt handler
    const handleBeforeInstallPrompt = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setIsInstallable(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    };
  }, []);

  const handleInstallClick = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === 'accepted') {
      setIsInstallable(false);
    }
    setDeferredPrompt(null);
  };

  if (isStandalone || dismissed) {
    return null;
  }

  return (
    <div className="bg-gradient-to-r from-[#141b2d] via-[#1a233a] to-[#121829] border border-amber-400/40 rounded-2xl p-4 shadow-[0_0_30px_rgba(245,200,66,0.15)] flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 backdrop-blur-xl">
      <div className="flex items-start sm:items-center gap-3.5">
        <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-gradient-to-tr from-amber-400 to-yellow-500 text-black font-extrabold text-xl shadow-lg shrink-0">
          FX
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-black text-white tracking-wide">
              INSTALL GOLD CLONE MOBILE APP
            </h3>
            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              NATIVE PWA
            </span>
          </div>
          <p className="text-xs text-slate-300 mt-0.5">
            {isIOS
              ? 'Tap the Share icon ⎋ at bottom of Safari, then select "Add to Home Screen" to install.'
              : 'Install directly to your home screen for full-screen trading, zero lag, and instant access.'}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
        {isInstallable && (
          <button
            onClick={handleInstallClick}
            className="flex-1 sm:flex-initial px-5 py-2.5 rounded-xl bg-gradient-to-r from-amber-400 via-yellow-400 to-amber-500 hover:from-amber-300 hover:to-yellow-400 text-black font-extrabold text-xs tracking-wider transition-all shadow-[0_0_15px_rgba(245,200,66,0.3)] active:scale-95 whitespace-nowrap"
          >
            INSTALL APP
          </button>
        )}
        <button
          onClick={() => setDismissed(true)}
          className="px-3 py-2 rounded-xl bg-white/[0.05] hover:bg-white/[0.1] text-slate-400 hover:text-slate-200 text-xs font-semibold transition-all"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
};

import { useState } from 'react';

interface EmergencyButtonProps {
  onKill: () => void;
}

export default function EmergencyButton({ onKill }: EmergencyButtonProps) {
  const [confirming, setConfirming] = useState(false);

  const handleClick = () => {
    if (!confirming) {
      setConfirming(true);
      setTimeout(() => setConfirming(false), 3000); // Auto-reset after 3 seconds
    } else {
      onKill();
      setConfirming(false);
    }
  };

  return (
    <button
      onClick={handleClick}
      className={`w-full py-4 rounded-xl font-bold text-lg transition-all ${
        confirming
          ? 'bg-red-600 text-white animate-pulse border-2 border-red-400'
          : 'bg-gradient-to-r from-red-600 to-red-700 text-white border border-red-500'
      }`}
    >
      {confirming ? '⚠️ CONFIRM KILL ALL ⚠️' : '🚨 EMERGENCY KILL SWITCH'}
    </button>
  );
}
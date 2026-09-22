import { TradingAccount } from '@/lib/types';

interface AccountCardProps {
  account: TradingAccount;
}

export default function AccountCard({ account }: AccountCardProps) {
  const isOnline = account.connection_status === 'connected';
  const dailyPnlClass = account.daily_profit_loss >= 0 ? 'text-green-500' : 'text-red-500';
  const dailyPnlSign = account.daily_profit_loss >= 0 ? '+' : '';

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 hover:border-amber-500 transition-all">
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="font-semibold text-white">{account.broker_name}</h3>
          <p className="text-gray-400 text-sm">{account.account_number}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isOnline ? 'bg-green-500' : 'bg-red-500'} ${isOnline ? 'animate-pulse' : ''}`}></div>
          <span className={`text-xs font-medium ${isOnline ? 'text-green-500' : 'text-red-500'}`}>
            {isOnline ? 'Online' : 'Offline'}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-3">
        <div>
          <p className="text-gray-400 text-xs mb-1">Balance</p>
          <p className="text-lg font-bold text-white">${account.balance.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-gray-400 text-xs mb-1">Equity</p>
          <p className="text-lg font-bold text-white">${account.equity.toFixed(2)}</p>
        </div>
      </div>

      <div className="flex justify-between items-center pt-3 border-t border-gray-800">
        <div>
          <p className="text-gray-400 text-xs mb-1">Daily P&L</p>
          <p className={`font-bold ${dailyPnlClass}`}>
            {dailyPnlSign}${account.daily_profit_loss.toFixed(2)}
          </p>
        </div>
        <div className="text-right">
          <p className="text-gray-400 text-xs mb-1">Risk %</p>
          <p className="font-bold text-amber-500">{account.risk_percentage}%</p>
        </div>
      </div>

      {!account.is_active && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <span className="text-xs text-gray-500 bg-gray-800 px-2 py-1 rounded">
            Account Inactive
          </span>
        </div>
      )}
    </div>
  );
}
'use client';

import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import { TradingAccount, DashboardStats } from '@/lib/types';
import AccountCard from '@/components/AccountCard';
import EmergencyButton from '@/components/EmergencyButton';

export default function Home() {
  const [accounts, setAccounts] = useState<TradingAccount[]>([]);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAccounts = async () => {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;

      const { data: accountsData, error } = await supabase
        .from('trading_accounts')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false });

      if (error) throw error;
      setAccounts(accountsData || []);

      // Calculate stats
      const activeAccounts = accountsData?.filter(acc => acc.is_active) || [];
      const totalBalance = activeAccounts.reduce((sum, acc) => sum + (acc.balance || 0), 0);
      const totalEquity = activeAccounts.reduce((sum, acc) => sum + (acc.equity || 0), 0);
      const dailyPnl = activeAccounts.reduce((sum, acc) => sum + (acc.daily_profit_loss || 0), 0);
      const onlineAccounts = activeAccounts.filter(acc => acc.connection_status === 'connected').length;

      setStats({
        total_accounts: accountsData?.length || 0,
        active_accounts: activeAccounts.length,
        total_balance: totalBalance,
        total_equity: totalEquity,
        daily_pnl: dailyPnl,
        online_accounts: onlineAccounts
      });
    } catch (error) {
      console.error('Error fetching accounts:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleRefresh = () => {
    setRefreshing(true);
    fetchAccounts();
  };

  const handleEmergencyKill = async () => {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;

      const { error } = await supabase
        .from('emergency_commands')
        .insert({
          user_id: user.id,
          command_type: 'KILL_ALL',
          status: 'pending'
        });

      if (error) throw error;
      alert('Emergency kill command sent! All positions will be closed.');
    } catch (error) {
      console.error('Error sending emergency command:', error);
      alert('Failed to send emergency command');
    }
  };

  useEffect(() => {
    fetchAccounts();
    // Refresh every 10 seconds
    const interval = setInterval(fetchAccounts, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-400">Loading your trading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white p-4 pb-24">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-amber-500 mb-2">Multi-Account Trader</h1>
        <p className="text-gray-400 text-sm">Real-time account monitoring & signals</p>
      </div>

      {/* Stats Overview */}
      {stats && (
        <div className="grid grid-cols-2 gap-3 mb-6">
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <p className="text-gray-400 text-xs mb-1">Total Balance</p>
            <p className="text-xl font-bold text-white">${stats.total_balance.toFixed(2)}</p>
          </div>
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <p className="text-gray-400 text-xs mb-1">Daily P&L</p>
            <p className={`text-xl font-bold ${stats.daily_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
              ${stats.daily_pnl.toFixed(2)}
            </p>
          </div>
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <p className="text-gray-400 text-xs mb-1">Active Accounts</p>
            <p className="text-xl font-bold text-amber-500">{stats.active_accounts}/{stats.total_accounts}</p>
          </div>
          <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
            <p className="text-gray-400 text-xs mb-1">Online Status</p>
            <p className="text-xl font-bold text-green-500">{stats.online_accounts} Connected</p>
          </div>
        </div>
      )}

      {/* Emergency Kill Button */}
      <div className="mb-6">
        <EmergencyButton onKill={handleEmergencyKill} />
      </div>

      {/* Account Cards */}
      <div className="mb-4 flex justify-between items-center">
        <h2 className="text-lg font-semibold text-white">Trading Accounts</h2>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="text-amber-500 text-sm font-medium disabled:opacity-50"
        >
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      {accounts.length === 0 ? (
        <div className="bg-gray-900 rounded-xl p-8 text-center border border-gray-800">
          <p className="text-gray-400 mb-4">No trading accounts connected</p>
          <button className="btn-primary w-full">Add Your First Account</button>
        </div>
      ) : (
        <div className="space-y-3">
          {accounts.map((account) => (
            <AccountCard key={account.id} account={account} />
          ))}
        </div>
      )}

      {/* Bottom Navigation */}
      <div className="fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 p-4">
        <div className="flex justify-around">
          <button className="flex flex-col items-center text-amber-500">
            <svg className="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
            <span className="text-xs">Dashboard</span>
          </button>
          <button className="flex flex-col items-center text-gray-400">
            <svg className="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
            <span className="text-xs">Signals</span>
          </button>
          <button className="flex flex-col items-center text-gray-400">
            <svg className="w-6 h-6 mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            <span className="text-xs">Accounts</span>
          </button>
        </div>
      </div>
    </div>
  );
}
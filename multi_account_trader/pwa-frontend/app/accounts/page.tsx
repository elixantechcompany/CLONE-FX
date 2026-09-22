'use client';

import { useState, useEffect } from 'react';
import { supabase } from '@/lib/supabase';
import { TradingAccount } from '@/lib/types';

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<TradingAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [formData, setFormData] = useState({
    account_number: '',
    broker_name: '',
    mt5_server: '',
    encrypted_password: '',
    risk_percentage: 1.0
  });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const fetchAccounts = async () => {
    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) return;

      const { data, error } = await supabase
        .from('trading_accounts')
        .select('*')
        .eq('user_id', user.id)
        .order('created_at', { ascending: false });

      if (error) throw error;
      setAccounts(data || []);
    } catch (error) {
      console.error('Error fetching accounts:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleAddAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    try {
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) {
        setError('You must be logged in to add accounts');
        return;
      }

      // Check current account count
      if (accounts.length >= 5) {
        setError('Maximum 5 trading accounts allowed per user');
        return;
      }

      const { data, error } = await supabase
        .from('trading_accounts')
        .insert({
          user_id: user.id,
          account_number: formData.account_number,
          broker_name: formData.broker_name,
          mt5_server: formData.mt5_server,
          encrypted_password: formData.encrypted_password,
          risk_percentage: formData.risk_percentage,
          is_active: true,
          connection_status: 'disconnected',
          balance: 0.0,
          equity: 0.0,
          daily_profit_loss: 0.0
        })
        .select()
        .single();

      if (error) {
        if (error.message.includes('Maximum 5 trading accounts')) {
          setError('Maximum 5 trading accounts allowed per user');
        } else {
          throw error;
        }
        return;
      }

      setSuccess('Account added successfully!');
      setShowAddForm(false);
      setFormData({
        account_number: '',
        broker_name: '',
        mt5_server: '',
        encrypted_password: '',
        risk_percentage: 1.0
      });
      fetchAccounts();

    } catch (error: any) {
      console.error('Error adding account:', error);
      setError(error.message || 'Failed to add account');
    }
  };

  const handleDeleteAccount = async (accountId: string) => {
    if (!confirm('Are you sure you want to delete this account?')) return;

    try {
      const { error } = await supabase
        .from('trading_accounts')
        .delete()
        .eq('id', accountId);

      if (error) throw error;

      setSuccess('Account deleted successfully');
      fetchAccounts();
    } catch (error) {
      console.error('Error deleting account:', error);
      setError('Failed to delete account');
    }
  };

  const handleToggleActive = async (accountId: string, currentStatus: boolean) => {
    try {
      const { error } = await supabase
        .from('trading_accounts')
        .update({ is_active: !currentStatus })
        .eq('id', accountId);

      if (error) throw error;
      fetchAccounts();
    } catch (error) {
      console.error('Error toggling account:', error);
      setError('Failed to update account status');
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-black">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-gray-400">Loading accounts...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white p-4 pb-24">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-amber-500 mb-2">Account Management</h1>
        <p className="text-gray-400 text-sm">
          {accounts.length}/5 accounts connected
        </p>
      </div>

      {/* Error/Success Messages */}
      {error && (
        <div className="bg-red-900/50 border border-red-500 text-red-200 p-4 rounded-xl mb-4">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-900/50 border border-green-500 text-green-200 p-4 rounded-xl mb-4">
          {success}
        </div>
      )}

      {/* Add Account Button */}
      {!showAddForm && accounts.length < 5 && (
        <button
          onClick={() => setShowAddForm(true)}
          className="w-full btn-primary mb-6"
        >
          + Add New Account
        </button>
      )}

      {/* Account Limit Warning */}
      {accounts.length >= 5 && (
        <div className="bg-amber-900/30 border border-amber-500 text-amber-200 p-4 rounded-xl mb-6">
          <p className="font-semibold">⚠️ Account Limit Reached</p>
          <p className="text-sm mt-1">You have reached the maximum of 5 trading accounts.</p>
        </div>
      )}

      {/* Add Account Form */}
      {showAddForm && (
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-6">
          <h2 className="text-lg font-semibold mb-4">Add New Account</h2>
          <form onSubmit={handleAddAccount} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Account Number</label>
              <input
                type="text"
                required
                value={formData.account_number}
                onChange={(e) => setFormData({...formData, account_number: e.target.value})}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-white focus:border-amber-500 focus:outline-none"
                placeholder="12345678"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Broker Name</label>
              <input
                type="text"
                required
                value={formData.broker_name}
                onChange={(e) => setFormData({...formData, broker_name: e.target.value})}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-white focus:border-amber-500 focus:outline-none"
                placeholder="Exness"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">MT5 Server</label>
              <input
                type="text"
                required
                value={formData.mt5_server}
                onChange={(e) => setFormData({...formData, mt5_server: e.target.value})}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-white focus:border-amber-500 focus:outline-none"
                placeholder="Exness-MT5Trial"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Password</label>
              <input
                type="password"
                required
                value={formData.encrypted_password}
                onChange={(e) => setFormData({...formData, encrypted_password: e.target.value})}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg p-3 text-white focus:border-amber-500 focus:outline-none"
                placeholder="••••••••"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Risk Percentage: {formData.risk_percentage}%</label>
              <input
                type="range"
                min="0.5"
                max="5.0"
                step="0.5"
                value={formData.risk_percentage}
                onChange={(e) => setFormData({...formData, risk_percentage: parseFloat(e.target.value)})}
                className="w-full"
              />
            </div>
            <div className="flex gap-3">
              <button
                type="submit"
                className="flex-1 btn-primary"
              >
                Add Account
              </button>
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="flex-1 bg-gray-700 text-white font-semibold py-3 rounded-lg border border-gray-600"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Accounts List */}
      <div className="space-y-3">
        {accounts.length === 0 ? (
          <div className="bg-gray-900 rounded-xl p-8 text-center border border-gray-800">
            <p className="text-gray-400 mb-4">No trading accounts connected</p>
            <button
              onClick={() => setShowAddForm(true)}
              className="btn-primary"
            >
              Add Your First Account
            </button>
          </div>
        ) : (
          accounts.map((account) => (
            <div key={account.id} className="bg-gray-900 rounded-xl p-4 border border-gray-800">
              <div className="flex justify-between items-start mb-3">
                <div>
                  <h3 className="font-semibold text-white">{account.broker_name}</h3>
                  <p className="text-gray-400 text-sm">{account.account_number}</p>
                </div>
                <div className="flex items-center gap-2">
                  <div className={`w-2 h-2 rounded-full ${account.connection_status === 'connected' ? 'bg-green-500' : 'bg-red-500'}`}></div>
                  <span className={`text-xs font-medium ${account.connection_status === 'connected' ? 'text-green-500' : 'text-red-500'}`}>
                    {account.connection_status}
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 mb-3">
                <div>
                  <p className="text-gray-400 text-xs mb-1">Balance</p>
                  <p className="text-lg font-bold text-white">${account.balance.toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-gray-400 text-xs mb-1">Risk %</p>
                  <p className="text-lg font-bold text-amber-500">{account.risk_percentage}%</p>
                </div>
              </div>

              <div className="flex gap-2 pt-3 border-t border-gray-800">
                <button
                  onClick={() => handleToggleActive(account.id, account.is_active)}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium ${
                    account.is_active 
                      ? 'bg-green-600 text-white' 
                      : 'bg-gray-700 text-gray-300'
                  }`}
                >
                  {account.is_active ? 'Active' : 'Inactive'}
                </button>
                <button
                  onClick={() => handleDeleteAccount(account.id)}
                  className="flex-1 bg-red-600 text-white py-2 rounded-lg text-sm font-medium"
                >
                  Delete
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Bottom Navigation */}
      <div className="fixed bottom-0 left-0 right-0 bg-gray-900 border-t border-gray-800 p-4">
        <div className="flex justify-around">
          <button className="flex flex-col items-center text-gray-400">
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
          <button className="flex flex-col items-center text-amber-500">
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
import { NextRequest, NextResponse } from 'next/server';
import { supabase } from '@/lib/supabase';

// GET all accounts for current user
export async function GET(request: NextRequest) {
  try {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { data, error } = await supabase
      .from('trading_accounts')
      .select('*')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false });

    if (error) throw error;

    return NextResponse.json({ accounts: data });
  } catch (error) {
    console.error('Error fetching accounts:', error);
    return NextResponse.json({ error: 'Failed to fetch accounts' }, { status: 500 });
  }
}

// POST create new account (with 5-account limit enforcement)
export async function POST(request: NextRequest) {
  try {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const { account_number, broker_name, mt5_server, encrypted_password, risk_percentage = 1.0 } = body;

    // Validate required fields
    if (!account_number || !broker_name || !mt5_server || !encrypted_password) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    // Check current account count
    const { data: existingAccounts, error: countError } = await supabase
      .from('trading_accounts')
      .select('id')
      .eq('user_id', user.id);

    if (countError) throw countError;

    if (existingAccounts && existingAccounts.length >= 5) {
      return NextResponse.json({ 
        error: 'Maximum 5 trading accounts allowed per user',
        current_count: existingAccounts.length 
      }, { status: 400 });
    }

    // Create new account
    const { data, error } = await supabase
      .from('trading_accounts')
      .insert({
        user_id: user.id,
        account_number,
        broker_name,
        mt5_server,
        encrypted_password,
        risk_percentage,
        is_active: true,
        connection_status: 'disconnected',
        balance: 0.0,
        equity: 0.0,
        daily_profit_loss: 0.0
      })
      .select()
      .single();

    if (error) throw error;

    return NextResponse.json({ account: data }, { status: 201 });
  } catch (error) {
    console.error('Error creating account:', error);
    return NextResponse.json({ error: 'Failed to create account' }, { status: 500 });
  }
}

// PUT update account
export async function PUT(request: NextRequest) {
  try {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const { id, ...updateData } = body;

    if (!id) {
      return NextResponse.json({ error: 'Account ID required' }, { status: 400 });
    }

    const { data, error } = await supabase
      .from('trading_accounts')
      .update(updateData)
      .eq('id', id)
      .eq('user_id', user.id)
      .select()
      .single();

    if (error) throw error;

    return NextResponse.json({ account: data });
  } catch (error) {
    console.error('Error updating account:', error);
    return NextResponse.json({ error: 'Failed to update account' }, { status: 500 });
  }
}

// DELETE account
export async function DELETE(request: NextRequest) {
  try {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');

    if (!id) {
      return NextResponse.json({ error: 'Account ID required' }, { status: 400 });
    }

    const { error } = await supabase
      .from('trading_accounts')
      .delete()
      .eq('id', id)
      .eq('user_id', user.id);

    if (error) throw error;

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Error deleting account:', error);
    return NextResponse.json({ error: 'Failed to delete account' }, { status: 500 });
  }
}
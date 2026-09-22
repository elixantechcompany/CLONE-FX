import { NextRequest, NextResponse } from 'next/server';
import { supabase } from '@/lib/supabase';

// POST emergency command
export async function POST(request: NextRequest) {
  try {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const { command_type } = body; // 'KILL_ALL', 'PAUSE_ALL', 'RESUME_ALL'

    if (!command_type || !['KILL_ALL', 'PAUSE_ALL', 'RESUME_ALL'].includes(command_type)) {
      return NextResponse.json({ error: 'Invalid command type' }, { status: 400 });
    }

    // Create emergency command
    const { data, error } = await supabase
      .from('emergency_commands')
      .insert({
        user_id: user.id,
        command_type,
        status: 'pending'
      })
      .select()
      .single();

    if (error) throw error;

    return NextResponse.json({ command: data }, { status: 201 });
  } catch (error) {
    console.error('Error creating emergency command:', error);
    return NextResponse.json({ error: 'Failed to create emergency command' }, { status: 500 });
  }
}

// GET emergency commands status
export async function GET(request: NextRequest) {
  try {
    const { data: { user } } = await supabase.auth.getUser();
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status');

    let query = supabase
      .from('emergency_commands')
      .select('*')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
      .limit(10);

    if (status) {
      query = query.eq('status', status);
    }

    const { data, error } = await query;

    if (error) throw error;

    return NextResponse.json({ commands: data });
  } catch (error) {
    console.error('Error fetching emergency commands:', error);
    return NextResponse.json({ error: 'Failed to fetch emergency commands' }, { status: 500 });
  }
}
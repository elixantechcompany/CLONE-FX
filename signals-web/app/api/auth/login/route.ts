import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

export const dynamic = 'force-dynamic';

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://xeckbeavsvyoporldjzm.supabase.co';
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { email, password } = body;

    if (!email || !password) {
      return NextResponse.json(
        { success: false, error: 'Email and password are required.' },
        { status: 400 }
      );
    }

    const anonClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: { persistSession: false },
    });

    let { data, error } = await anonClient.auth.signInWithPassword({
      email,
      password,
    });

    // If error is email_not_confirmed, use admin client to auto-confirm and re-attempt
    if (error && error.message.includes('not confirmed') && SUPABASE_SERVICE_ROLE_KEY) {
      const adminClient = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
        auth: { persistSession: false },
      });
      // Find user and confirm
      const { data: userData } = await adminClient.auth.admin.listUsers();
      const matched = userData?.users.find((u) => u.email?.toLowerCase() === email.toLowerCase());
      if (matched) {
        await adminClient.auth.admin.updateUserById(matched.id, { email_confirm: true });
        const retry = await anonClient.auth.signInWithPassword({ email, password });
        data = retry.data;
        error = retry.error;
      }
    }

    if (error) {
      return NextResponse.json({ success: false, error: error.message }, { status: 400 });
    }

    const userMeta = data.user?.user_metadata || {};
    return NextResponse.json({
      success: true,
      token: data.session?.access_token,
      user: {
        id: data.user.id,
        email: data.user.email,
        name: userMeta.name || email.split('@')[0],
        accountType: userMeta.account_type || 'PERSONAL',
      },
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message || 'Login failed' }, { status: 500 });
  }
}

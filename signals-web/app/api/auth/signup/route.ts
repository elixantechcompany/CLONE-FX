import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';

export const dynamic = 'force-dynamic';

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL || 'https://xeckbeavsvyoporldjzm.supabase.co';
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';
const SUPABASE_ANON_KEY = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || '';

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { email, password, name, account_type } = body;

    if (!email || !password) {
      return NextResponse.json(
        { success: false, error: 'Email and password are required.' },
        { status: 400 }
      );
    }

    if (password.length < 6) {
      return NextResponse.json(
        { success: false, error: 'Password must be at least 6 characters.' },
        { status: 400 }
      );
    }

    const traderName = name || email.split('@')[0];
    const traderType = account_type || 'PERSONAL';

    // 1. If service role key is available, create user with auto email confirmation
    if (SUPABASE_SERVICE_ROLE_KEY) {
      const adminClient = createClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, {
        auth: { persistSession: false },
      });

      // Try creating pre-confirmed user
      const { data: adminData, error: adminError } = await adminClient.auth.admin.createUser({
        email,
        password,
        email_confirm: true,
        user_metadata: {
          name: traderName,
          account_type: traderType,
        },
      });

      if (adminError && !adminError.message.includes('already registered')) {
        return NextResponse.json({ success: false, error: adminError.message }, { status: 400 });
      }
    }

    // 2. Sign in to get active session
    const anonClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: { persistSession: false },
    });

    const { data: signInData, error: signInError } = await anonClient.auth.signInWithPassword({
      email,
      password,
    });

    if (signInError) {
      return NextResponse.json({
        success: true,
        message: 'Account registered successfully. Please sign in.',
        user: {
          email,
          name: traderName,
          accountType: traderType,
        },
      });
    }

    return NextResponse.json({
      success: true,
      message: 'Account created and logged in!',
      token: signInData.session?.access_token,
      user: {
        id: signInData.user.id,
        email: signInData.user.email,
        name: traderName,
        accountType: traderType,
      },
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message || 'Signup failed' }, { status: 500 });
  }
}

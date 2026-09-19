import { NextRequest, NextResponse } from 'next/server';
import { getJournalEntries, saveJournalEntry, deleteJournalEntry } from '@/lib/supabase';
import { JournalEntry } from '@/lib/types';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const userEmail = searchParams.get('email') || undefined;
    const entries = await getJournalEntries(userEmail);
    return NextResponse.json({ entries });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body: JournalEntry = await req.json();

    if (!body.symbol || !body.order_action || !body.entry_price) {
      return NextResponse.json(
        { error: 'Missing required trade parameters (symbol, order_action, entry_price).' },
        { status: 400 }
      );
    }

    const saved = await saveJournalEntry(body);
    return NextResponse.json({ success: true, entry: saved });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const id = searchParams.get('id');
    if (!id) {
      return NextResponse.json({ error: 'Missing id parameter.' }, { status: 400 });
    }
    const success = await deleteJournalEntry(id);
    return NextResponse.json({ success });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

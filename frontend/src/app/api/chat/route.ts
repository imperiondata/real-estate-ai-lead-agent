import { NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL;
const WIDGET_API_KEY = process.env.WIDGET_API_KEY;

type ChatBody = {
  session_id?: string;
  message?: string;
};

export async function POST(request: Request) {
  if (!BACKEND_URL || !WIDGET_API_KEY) {
    return NextResponse.json(
      { error: 'Chat backend is not configured.' },
      { status: 503 },
    );
  }

  let body: ChatBody;
  try {
    body = (await request.json()) as ChatBody;
  } catch {
    return NextResponse.json({ error: 'Invalid JSON body.' }, { status: 400 });
  }

  const sessionId = (body.session_id ?? '').trim();
  const message = (body.message ?? '').trim();
  if (!sessionId || !message) {
    return NextResponse.json(
      { error: 'session_id and message are required.' },
      { status: 400 },
    );
  }

  const url = new URL(`${BACKEND_URL}/api/v1/chat`);
  url.searchParams.set('session_id', sessionId);
  url.searchParams.set('message', message);

  try {
    const res = await fetch(url.toString(), {
      method: 'POST',
      headers: { 'X-API-Key': WIDGET_API_KEY },
      cache: 'no-store',
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) {
      return NextResponse.json(
        { error: data?.detail ?? 'Chat request failed.' },
        { status: res.status },
      );
    }
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(
      { error: 'Chat backend unreachable.' },
      { status: 502 },
    );
  }
}

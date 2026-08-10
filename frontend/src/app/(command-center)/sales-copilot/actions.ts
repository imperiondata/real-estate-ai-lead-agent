'use server';

import { cookies } from 'next/headers';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function getNextBestAction(leadId: string) {
  const cookieStore = await cookies();
  const token = cookieStore.get('jwt')?.value;

  if (!token) {
    throw new Error('Unauthorized');
  }

  const res = await fetch(`${BACKEND_URL}/api/v1/leads/${leadId}/sales-ai`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    cache: 'no-store'
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch Sales AI: ${res.status}`);
  }

  return await res.json();
}

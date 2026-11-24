import { Router } from 'express';
import { livekitAPI } from '../lib/livekit.js';
const router = Router();
router.post('/sessions/cleanup', async (_req, res) => {
  if (!((process.env.LIVEKIT_API_URL || process.env.LIVEKIT_URL) && process.env.LIVEKIT_API_KEY && process.env.LIVEKIT_API_SECRET)) return res.status(503).json({ error: 'اطلاعات LiveKit در فایل .env تنظیم نشده است.' });
  try {
    const api = livekitAPI();
    const rooms = await api.room.listRooms();
    const stale = rooms.filter((room) => String(room.name || '').startsWith('sam-'));
    for (const room of stale) await api.room.deleteRoom(room.name);
    res.json({ closedRooms: stale.map((room) => room.name) });
  } catch (error) {
    console.error('Could not close stale sessions:', error);
    res.status(502).json({ error: 'بستن نشست‌های باز ناموفق بود.', details: process.env.NODE_ENV === 'production' ? undefined : (error instanceof Error ? error.message : String(error)) });
  }
});
export default router;

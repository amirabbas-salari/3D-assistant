export function corsMiddleware(req, res, next) {
  const allowed = (process.env.WIDGET_ALLOWED_ORIGINS || '*').trim();
  res.header('Access-Control-Allow-Origin', allowed === '*' ? '*' : allowed.split(',')[0].trim());
  res.header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
  res.header('Permissions-Policy', 'microphone=(self "*"), camera=(self "*"), autoplay=(self "*")');
  if (req.method === 'OPTIONS') return res.sendStatus(204);
  next();
}

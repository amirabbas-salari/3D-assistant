import 'dotenv/config';
import express from 'express';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { corsMiddleware } from './config/cors.js';
import healthRouter from './routes/health.js';
import sessionRouter from './routes/session.js';
import cleanupRouter from './routes/cleanup.js';

const app = express();
const port = Number(process.env.PORT || 3001);
const __dirname = path.dirname(fileURLToPath(import.meta.url));

app.use(express.json({ limit: '32kb' }));
app.use(corsMiddleware);

app.use('/api', healthRouter);
app.use('/api', sessionRouter);
app.use('/api', cleanupRouter);

if (process.env.NODE_ENV === 'production') {
  const candidates = [
    path.resolve(__dirname, '../web/dist'),
    path.resolve(__dirname, '../../web/dist'),
    path.resolve(__dirname, '../../../dist'),
    path.resolve(__dirname, '../dist'),
    path.resolve(__dirname, '../../dist'),
  ];
  const clientDist = candidates.find((p) => fs.existsSync(p)) || candidates[0];
  app.use(express.static(clientDist));
  app.get('*', (_req, res) => res.sendFile(path.join(clientDist, 'index.html')));
}

app.listen(port, '0.0.0.0', () => console.log(`API server listening on http://0.0.0.0:${port}`));

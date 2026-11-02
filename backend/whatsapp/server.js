const express = require('express');
const { Client, LocalAuth } = require('whatsapp-web.js');
const QRCode = require('qrcode');
const fs = require('fs');
const path = require('path');

const PORT = process.env.PORT || 8020;
const SESSION_DIR = process.env.SESSION_DIR || path.join(__dirname, '..', '..', 'data', 'whatsapp_session');
const QR_FILE = path.join(__dirname, '..', '..', 'data', 'whatsapp_qr.txt');
const STATUS_FILE = path.join(__dirname, '..', '..', 'data', 'whatsapp_status.txt');

fs.mkdirSync(SESSION_DIR, { recursive: true });

let ready = false;
let qrCodeData = null;
let status = 'initializing';

function writeStatus() {
  fs.writeFileSync(STATUS_FILE, JSON.stringify({ ready, status, qr: !!qrCodeData, updated_at: new Date().toISOString() }));
}

const client = new Client({
  authStrategy: new LocalAuth({ dataPath: SESSION_DIR }),
  puppeteer: {
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  },
});

client.on('qr', async (qr) => {
  qrCodeData = qr;
  status = 'awaiting_qr';
  try {
    const qrDataUrl = await QRCode.toDataURL(qr, { width: 400, margin: 2 });
    fs.writeFileSync(QR_FILE, qrDataUrl);
  } catch (e) {
    fs.writeFileSync(QR_FILE, qr);
  }
  writeStatus();
  console.log('[whatsapp-web] QR code generated. Scan it in Settings > WhatsApp Web.');
});

client.on('ready', () => {
  ready = true;
  status = 'ready';
  qrCodeData = null;
  try { fs.unlinkSync(QR_FILE); } catch (e) {}
  writeStatus();
  console.log('[whatsapp-web] Client is ready.');
});

client.on('disconnected', () => {
  ready = false;
  status = 'disconnected';
  writeStatus();
  console.log('[whatsapp-web] Disconnected.');
});

client.on('auth_failure', (msg) => {
  status = 'auth_failure';
  writeStatus();
  console.error('[whatsapp-web] Auth failure:', msg);
});

client.initialize();

function normalizePhone(phone) {
  let digits = phone.replace(/\D/g, '');
  if (digits.startsWith('0') && digits.length >= 9) {
    digits = '971' + digits.slice(1);
  } else if (digits.startsWith('5') && digits.length === 9) {
    digits = '971' + digits;
  } else if (digits.startsWith('05') && digits.length === 10) {
    digits = '971' + digits.slice(1);
  }
  return digits;
}

const app = express();
app.use(express.json());

app.get('/status', (req, res) => {
  let qrImage = null;
  try {
    if (fs.existsSync(QR_FILE)) {
      qrImage = fs.readFileSync(QR_FILE, 'utf8');
    }
  } catch (e) {}
  res.json({ ready, status, qr_image: qrImage });
});

app.post('/send', async (req, res) => {
  if (!ready) {
    return res.status(503).json({ error: 'WhatsApp Web not ready. Scan QR code first.' });
  }
  const { to, message } = req.body;
  if (!to || !message) {
    return res.status(400).json({ error: 'Missing to or message' });
  }
  const digits = normalizePhone(to);
  const chatId = `${digits}@c.us`;
  try {
    await client.sendMessage(chatId, message);
    res.json({ success: true, to: digits });
  } catch (e) {
    console.error('[whatsapp-web] Send failed:', e.message);
    res.status(500).json({ error: e.message });
  }
});

app.listen(PORT, '127.0.0.1', () => {
  console.log(`[whatsapp-web] Bridge server listening on http://127.0.0.1:${PORT}`);
});

const http = require('http');
const crypto = require('crypto');

const PORT = process.env.PORT || 3000;

const server = http.createServer((req, res) => {
  if (req.method === 'GET' && req.url === '/healthz') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ status: 'ok', service: 'payment-service', healthy: true }));
    return;
  }

  if (req.method === 'POST' && req.url === '/charge') {
    let body = '';
    req.on('data', chunk => { body += chunk; });
    req.on('end', () => {
      const delay = Math.floor(Math.random() * 200) + 100;
      setTimeout(() => {
        const txId = 'tx_' + crypto.randomBytes(8).toString('hex');
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          status: 'success',
          tx_id: txId,
          amount: 49.99,
          currency: 'USD',
          timestamp: new Date().toISOString()
        }));
      }, delay);
    });
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Not Found' }));
});

server.listen(PORT, '0.0.0.0', () => {
  console.log(`[payment-service] Listening on port ${PORT}`);
});

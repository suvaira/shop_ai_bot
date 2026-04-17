const slug = window.location.pathname.split('/').filter(Boolean).pop();
const form = document.getElementById('chat-form');
const input = document.getElementById('msg');
const box = document.getElementById('chat-box');
const statusEl = document.getElementById('status');
const shopTitle = document.getElementById('shop-title');

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').catch(() => {});
}

let shopName = slug;
let offlineConfig = JSON.parse(localStorage.getItem(`shop-config-${slug}`) || '{}');

const addMessage = (text, cls) => {
  const div = document.createElement('div');
  div.className = `msg ${cls}`;
  div.textContent = text;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
};

const offlineReply = (msg) => {
  const message = msg.toLowerCase();
  const qna = offlineConfig.qna || [];
  for (const pair of qna) {
    if (message.includes(String(pair.question || '').toLowerCase())) return pair.answer;
  }

  if (message.includes('timing') && offlineConfig.timings) {
    return `Shop timings: ${offlineConfig.timings}`;
  }

  if ((message.includes('return') || message.includes('refund')) && offlineConfig.rules?.length) {
    return `Policy: ${offlineConfig.rules[0]}`;
  }

  return `Offline mode: ${shopName} assistant limited mode me hai. Specific question poochiye.`;
};

const loadShopMeta = async () => {
  try {
    const res = await fetch(`/api/shops/${slug}`);
    if (!res.ok) throw new Error('shop fetch failed');
    const data = await res.json();
    shopName = data.name || slug;
    offlineConfig = data.config || offlineConfig;
    localStorage.setItem(`shop-config-${slug}`, JSON.stringify(offlineConfig));
    shopTitle.textContent = `${shopName} - AI Assistant`;
  } catch (_) {
    shopTitle.textContent = `${shopName} - AI Assistant`;
  }
  addMessage(`Namaste! Main ${shopName} ka AI assistant hoon.`, 'bot');
};

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const message = input.value.trim();
  if (!message) return;

  addMessage(message, 'user');
  input.value = '';

  try {
    const res = await fetch(`/api/shops/${slug}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Request failed');

    statusEl.textContent = 'Status: online mode';
    addMessage(data.reply, 'bot');
  } catch (err) {
    statusEl.textContent = 'Status: offline fallback mode';
    addMessage(offlineReply(message), 'bot');
  }
});

loadShopMeta();

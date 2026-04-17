const form = document.getElementById('shop-form');
const result = document.getElementById('result');
const link = document.getElementById('shop-link');
const ownerKeyEl = document.getElementById('owner-key');

const parseLines = (value) => value
  .split('\n')
  .map((line) => line.trim())
  .filter(Boolean);

const parseCSV = (value) => value
  .split(',')
  .map((v) => v.trim())
  .filter(Boolean);

const parseQnA = (value) => parseLines(value).map((line) => {
  const [question, answer] = line.split('=>').map((x) => (x || '').trim());
  return { question, answer };
}).filter((pair) => pair.question && pair.answer);

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(form);

  const payload = {
    name: fd.get('name'),
    timings: fd.get('timings'),
    products: parseCSV(fd.get('products') || ''),
    rules: parseLines(fd.get('rules') || ''),
    qna: parseQnA(fd.get('qna') || ''),
  };

  const res = await fetch('/api/shops', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  const data = await res.json();
  if (!res.ok) {
    alert(data.error || 'Unable to create shop');
    return;
  }

  localStorage.setItem(`shop-config-${data.slug}`, JSON.stringify(payload));
  localStorage.setItem(`shop-owner-key-${data.slug}`, data.owner_key);

  result.hidden = false;
  link.href = data.url;
  link.textContent = data.full_url;
  ownerKeyEl.textContent = data.owner_key;
});
